# Jupyterpost: post from Jupyterhub to a Mattermost server

## Installing

`pip install jupyterpost`

## Enabling jupyterpost

1. Create a bot user on your Mattermost server and get its token.
2. Add the following at the end of your Jupyterhub config file.

```python
from jupyterpost import configure_jupyterhub

configure_jupyterhub(
    c,
    mattermost_token="your mattermost token",
    mattermost_url="https://your.mattermost.server/api/v4/",
    mattermost_team="your mattermost team name",
    jupyterpost_url="https://services.your.jupyterhub/services/jupyterpost",
)
```
This will:

* add a new service `jupyterpost` to your Jupyterhub
* give all users *and their servers* access to this service
* provide the service URL to the user's server as an environment variable `JUPYTERPOST_URL`

The function is somewhat fragile, but should work for standard Jupyterhub installations.

## Using jupyterpost

The low level interface to Jupyterpost is `jupyterpost.post`. It takes a message, a channel, and an attachment, and posts it to the Mattermost server.
```python
from jupyterpost import post
from matplotlib import pyplot

pyplot.plot([0, 1])
post(
    message="Check out my plot",
    channel="my-channel",  # Or "@username"
    attachment=pyplot.gcf(),  # Or png bytes
)
```
In practice, however, you will probably want to use the `%post`/`%%post` magic commands.
Both become available after importing `jupyterpost`.
The line magic is meant for short messages:
```ipython
run_long_computation()
%post @myself Computation done!
```
The cell magic can:
- Post a multiline formatted message with a `-r` argument

    ```ipython
    %%post <channel> -r
    ## Markdown title
    - Anything
    - Goes
    ```
- Post the cell outputs (latex, plain text, markdown), and a single image (for now)
- Optionally include the cell input with a `-i` argument

    ```ipython
    %%post <channel> -i
    import matplotlib.pyplot as plt
    plt.plot([0, 1])
    ```

### Posting from outside of your Jupyterhub

1. Get the variables `JUPYTERPOST_URL` and `JPY_API_TOKEN` from your Jupyterhub server.
2. Provide them to `jupyterpost.post` as additional arguments and connect from anywhere!

## Contributing

Contributions are welcome! Please open an issue or a pull request.

Specifically I would like to support more chat services, and more ways to post messages.

Tests would also be great huehuehue.
