"""Safe, optional integrations used by CodeAtlas intelligence views."""

from .dependencies import extract_dependencies
from .github import GithubClient
from .npm import NpmClient
from .osv import OsvClient
from .pypi import PypiClient

__all__ = ["GithubClient", "NpmClient", "OsvClient", "PypiClient", "extract_dependencies"]
