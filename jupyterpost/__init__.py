"""Jupyterpost: Jupyterhub service for posting to Mattermost."""

__version__ = "0.0.1"

from .jupyterpost import (
    configure_jupyterhub, hub_post_message, main, post
)
