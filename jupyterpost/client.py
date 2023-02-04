from io import BytesIO
import os
from base64 import b64decode

import httpx
from IPython.core.magic import Magics, magics_class, line_cell_magic
from IPython.core import magic_arguments
from IPython import get_ipython
from IPython.utils.capture import capture_output


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


@magics_class
class JupyterpostMagics(Magics):
    @magic_arguments.magic_arguments()
    @magic_arguments.argument(
        "channel",
        type=str,
        help=(
            "The channel to post to. If it starts with '@', "
            "it is assumed to be a direct message to the user with that username."
        ),
    )
    @magic_arguments.argument(
        "message",
        nargs="*",
        default="",
        type=str,
        help="The message to post.",
    )
    @magic_arguments.argument(
        "-i",
        "--input",
        action="store_true",
        help="Add formatted cell source to the message.",
    )
    @magic_arguments.argument(
        "-r",
        "--raw",
        action="store_true",
        help=(
            "Post the cell source as raw text to keep formatting."
            "Does not execute the cell."
        ),
    )
    @magic_arguments.argument(
        "--url",
        type=str,
        help=(
            "The URL of the JupyterHub service. "
            "Not required if running in configured JupyterHub."
        ),
    )
    @magic_arguments.argument(
        "--token",
        type=str,
        help="The API token to use. Not required if running in configured JupyterHub.",
    )
    @line_cell_magic
    def post(self, line, cell=None):
        """Post a message to Mattermost using the JupyterHub service."""
        args = magic_arguments.parse_argstring(self.post, line)
        message = " ".join(args.message)
        if cell is None:
            if not message:
                raise ValueError("No message given")
            post(message, args.channel, service_url=args.url, token=args.token)
            return
        message = [message] if message else ["​"] # Zero-width space for linebreaks
        if args.raw:
            message = "\n".join((message[0], cell))
            post(message, args.channel, service_url=args.url, token=args.token)
            return

        if args.input:
            message.append(f"```python{cell}```")

        # Execute the cell
        with capture_output() as captured:
            self.shell.run_cell(cell)

        captured.show()
        message += captured.stdout
        attachments = []
        for output in captured.outputs:
            for mime_type in [
                "image/png",
                # TODO: support other images
                # "image/jpeg", "image/svg+xml",
                "text/markdown",
                "text/latex",
                "text/plain",
            ]:
                if mime_type not in output.data:
                    continue
                if mime_type.startswith("image"):
                    attachments.append(output.data[mime_type])
                    break
                elif mime_type == "text/plain":
                    # Treat as preformatted text
                    message.append(f"```\n{output.data[mime_type]}\n```")
                else:
                    message.append(output.data[mime_type])
                    break

        message = "\n".join(message)
        if not message and not attachments:
            raise ValueError("No message or attachments given")
        # TODO: support multiple attachments
        post(
            message,
            args.channel,
            b64decode(attachments[0]) if attachments else None,
            service_url=args.url,
            token=args.token,
        )


def load_ipython_extension(ipython):
    ipython.register_magics(JupyterpostMagics)


# Try and initialize the magics on import
try:
    get_ipython().register_magics(JupyterpostMagics)
except AttributeError:
    pass
