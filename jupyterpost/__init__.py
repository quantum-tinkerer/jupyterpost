"""Jupyterpost: Jupyterhub service for posting to Mattermost."""

__version__ = "0.0.2"

from .jupyterpost import configure_jupyterhub, hub_post_message, main
from .client import post, load_ipython_extension


__all__ = [
    "configure_jupyterhub",
    "hub_post_message",
    "main",
    "post",
    "load_ipython_extension",
]
