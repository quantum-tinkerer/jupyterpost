"""JupyterPost: JupyterHub Service to post messages to Mattermost.

Modeled after the JupyterHub Service example at
https://github.com/jupyterhub/jupyterhub/tree/main/examples/service-whoami
"""
import os
from urllib.parse import urlparse
import logging
from io import BytesIO

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler, authenticated
import httpx

from jupyterhub.services.auth import HubAuthenticated
from jupyterhub.roles import get_default_roles
from jupyterhub.app import JupyterHub

logger = logging.getLogger("jupyterpost")
logger.setLevel(logging.INFO)


async def mm_api_call(method, path, **kwargs):
    """Make an API call to Mattermost.

    Parameters
    ----------
    method : str
        The HTTP method to use.
    path : str
        The API URL to call. The base URL will be taken from the
        MATTERMOST_URL environment variable.
    **kwargs : dict
        Additional keyword arguments to pass to httpx.request.

    Returns
    -------
    response
        The JSON response from the API call.
    """
    url = os.environ["MATTERMOST_URL"] + path
    token = os.environ["MATTERMOST_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
    return response.json()


async def hub_post_message(message, channel, file_=None, team_name=None):
    """Post a message to Mattermost from the JupyterHub service.

    Parameters
    ----------
    message : str
        The message to post.
    channel : str
        The channel to post to. If it starts with '@', it is assumed to be a
        direct message to the user with that username.
    file_ : bytes, optional
        A file to upload. If given, will be attached to the message.
    team_name : str, optional
        The name of the team to post to. If not given, will be taken from the
        MATTERMOST_TEAM environment variable.
    """
    team_name = team_name or os.getenv("MATTERMOST_TEAM")
    me = (await mm_api_call("get", "users/me"))["id"]
    if channel.startswith("@"):
        # A direct message
        try:
            other = (await mm_api_call("get", f"users/username/{channel[1:]}"))["id"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # User does not exist
                raise ValueError(f"{channel} does not exist")
            else:
                raise
        # Check if they are a member of the team
        team_id = (await mm_api_call("get", f"teams/name/{team_name}"))["id"]
        try:
            await mm_api_call("get", f"teams/{team_id}/members/{other}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Not a member, refuse to post
                raise ValueError(f"{channel} is not a member of {team_name}")
            else:
                raise
        channel = await mm_api_call("post", "channels/direct", json=[me, other])
    else:
        try:
            channel = await mm_api_call(
                "get", f"teams/name/{team_name}/channels/name/{channel}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Channel does not exist or is private
                raise ValueError(f"{channel} does not exist or is private")
            else:
                raise
        # Join the channel (this is idempotent)
        await mm_api_call(
            "post", f"channels/{channel['id']}/members", json={"user_id": me}
        )

    channel_id = channel["id"]

    if file_:  # Upload the file
        upload = await mm_api_call(
            "post",
            "files",
            params={"channel_id": channel_id, "filename": "upload.png"},
            data=file_,
        )
        file_ids = [upload["file_infos"][0]["id"]]
    else:
        file_ids = []
    return await mm_api_call(
        "post",
        "posts",
        json={"channel_id": channel_id, "message": message, "file_ids": file_ids},
    )


class ChatPostHandler(HubAuthenticated, RequestHandler):
    @authenticated
    async def post(self):
        username = self.get_current_user()["name"]
        message = self.get_argument("message")
        message = f"*@{username} {os.getenv('BOT_SIGNATURE')}*: {message}"
        channel = self.get_argument("channel")
        file_ = self.request.files.get("file", [{"body": None}])[0]["body"]
        try:
            await hub_post_message(message, channel, file_)
        except ValueError as e:
            self.set_status(400)
            self.write(str(e))


def configure_jupyterhub(
    c,
    mattermost_token: str,
    mattermost_url: str,
    mattermost_team: str,
    port: int = 10101,
    bot_signature: str = "(via jupyterpost)",
    jupyterpost_url: str = None,
):
    """Configure JupyterHub to use this service.

    Parameters
    ----------
    c : Config
        The JupyterHub config object to modify.
    mattermost_token : str
        The Mattermost API token to use.
    mattermost_url : str
        The base API URL of the Mattermost server.
    mattermost_team : str
        The name of the Mattermost team to post to.
    port : int, optional
        The port to run the service on. Defaults to 10101.
    bot_signature : str, optional
        The signature to add to messages posted by the bot. Defaults to
        "(via jupyterpost)".
    jupyterpost_url : str, optional
        The URL to use for the service. TODO: Should be inferred from the config,
        but this doesn't work well yet.
    """
    c.JupyterHub.services.append(
        {
            "name": "jupyterpost",
            "url": f"http://127.0.0.1:{port}",
            "command": ["jupyterpost"],
            "environment": {
                "MATTERMOST_TOKEN": mattermost_token,
                "MATTERMOST_URL": mattermost_url,
                "MATTERMOST_TEAM": mattermost_team,
                "BOT_SIGNATURE": bot_signature,
            },
        }
    )
    default_roles = {r["name"]: r for r in get_default_roles()}
    roles = {r["name"]: r for r in c.JupyterHub.load_roles}
    user_role = roles.get("user", default_roles["user"])
    server_role = roles.get("server", default_roles["server"])
    user_role["scopes"].append("access:services!service=jupyterpost")
    server_role["scopes"].append("access:services!service=jupyterpost")
    c.JupyterHub.load_roles = [
        r for name, r in roles.items() if name not in "user server"
    ] + [user_role, server_role]
    try:
        environment = c.Spawner.environment.to_dict()
    except AttributeError:
        # Already a dict
        environment = c.Spawner.environment
    c.Spawner.environment = {
        **environment,
        "JUPYTERPOST_URL": jupyterpost_url
        or JupyterHub(config=c).bind_url + "services/jupyterpost",
    }


def post(message, channel, attachment=None, service_url=None, token=None):
    """Post a message to Mattermost using the JupyterHub service.

    Parameters
    ----------
    message : str
        The message to post.
    channel : str
        The channel to post to. If it starts with '@', it is assumed to be a
        direct message to the user with that username.
    attachment : bytes or matplotlib figure, optional
        A png file to upload. If given, will be attached to the message.
    service_url : str, optional
        The URL of the JupyterHub service. If not given, will be taken from the
        JUPYTERPOST_URL environment variable.
    token : str, optional
        The API token to use. If not given, will be taken from the
        JPY_API_TOKEN environment variable.
    """
    service_url = service_url or os.getenv("JUPYTERPOST_URL")
    token = token or os.getenv("JPY_API_TOKEN")
    if not service_url:
        raise ValueError("No service URL given")
    if not token:
        raise ValueError("No API token given")
    if attachment and not isinstance(attachment, bytes):
        data = BytesIO()
        try:
            attachment.savefig(data, format="png")
        except AttributeError:
            raise TypeError("attachment must be a bytes object or matplotlib figure")
        attachment = data.getvalue()

    response = httpx.post(
        service_url,
        headers={"Authorization": f"token {token}"},
        data={"message": message, "channel": channel},
        files={"file": attachment} if attachment else None,
    )
    if response.is_error:
        raise ValueError(response.text)


def main():
    app = Application(
        [
            (os.environ["JUPYTERHUB_SERVICE_PREFIX"] + "/?", ChatPostHandler),
            (r".*", ChatPostHandler),
        ],
        autoreload=True,
        debug=True,
    )
    http_server = HTTPServer(app)
    url = urlparse(os.environ["JUPYTERHUB_SERVICE_URL"])

    http_server.listen(url.port, url.hostname)

    IOLoop.current().start()


if __name__ == "__main__":
    main()
