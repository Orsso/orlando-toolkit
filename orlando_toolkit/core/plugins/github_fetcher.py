"""
GitHub metadata fetcher for Orlando Toolkit plugin system.

Fetches plugin information from GitHub repositories without downloading
the entire repository, using GitHub's Contents API.
"""

import json
import re
import base64
from typing import Dict, Optional, Tuple
import requests


class GitHubMetadataFetcher:
    """Fetches plugin metadata and images from GitHub repositories."""
    
    def __init__(self):
        """Initialize the GitHub metadata fetcher."""
        self.api_base = "https://api.github.com"
        self.timeout = 10  # seconds
    
    def fetch_plugin_info(self, repo_url: str) -> dict:
        """
        Fetch plugin metadata and image from GitHub repository.
        
        Args:
            repo_url: GitHub repository URL (https://github.com/owner/repo)
            
        Returns:
            dict: Combined plugin information with format:
                {
                    "metadata": {...},  # parsed plugin.json
                    "image_data": bytes or None,
                    "has_image": bool,
                    "repo_url": str,
                    "error": str or None
                }
        """
        try:
            # Parse repository URL
            owner, repo = self._parse_repo_url(repo_url)
            if not owner or not repo:
                return {
                    "metadata": None,
                    "image_data": None,
                    "has_image": False,
                    "repo_url": repo_url,
                    "error": "Invalid GitHub repository URL"
                }
            
            # Fetch plugin.json (required)
            metadata = self._fetch_plugin_json(owner, repo)
            if "error" in metadata:
                return {
                    "metadata": None,
                    "image_data": None,
                    "has_image": False,
                    "repo_url": repo_url,
                    "error": metadata["error"]
                }
            
            # Fetch plugin-icon.png (optional)
            image_data = self._fetch_plugin_image(owner, repo)
            
            return {
                "metadata": metadata,
                "image_data": image_data,
                "has_image": image_data is not None,
                "repo_url": repo_url,
                "error": None
            }
            
        except Exception as e:
            return {
                "metadata": None,
                "image_data": None,
                "has_image": False,
                "repo_url": repo_url,
                "error": f"Unexpected error: {str(e)}"
            }
    
    def _parse_repo_url(self, repo_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse GitHub repository URL to extract owner and repository name.
        
        Args:
            repo_url: GitHub repository URL
            
        Returns:
            tuple: (owner, repo) or (None, None) if invalid
        """
        # Support various GitHub URL formats
        patterns = [
            r'https://github\.com/([^/]+)/([^/]+)/?$',
            r'https://github\.com/([^/]+)/([^/]+)\.git$',
            r'git@github\.com:([^/]+)/([^/]+)\.git$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, repo_url.strip())
            if match:
                owner, repo = match.groups()
                # Remove .git suffix if present
                if repo.endswith('.git'):
                    repo = repo[:-4]
                return owner, repo
        
        return None, None
    
    def _fetch_plugin_json(self, owner: str, repo: str) -> dict:
        """
        Fetch plugin.json from GitHub repository via Contents API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            dict: Parsed plugin.json content or error information
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/contents/plugin.json"
            
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 404:
                return {"error": "plugin.json not found in repository"}
            elif response.status_code != 200:
                return {"error": f"Failed to fetch plugin.json: HTTP {response.status_code}"}
            
            # Parse GitHub API response
            content_info = response.json()
            
            if content_info.get("type") != "file":
                return {"error": "plugin.json is not a file"}
            
            # Decode base64 content
            if "content" not in content_info:
                return {"error": "No content found in plugin.json"}
            
            try:
                content_bytes = base64.b64decode(content_info["content"])
                content_str = content_bytes.decode('utf-8')
                plugin_metadata = json.loads(content_str)
                return plugin_metadata
            except (base64.binascii.Error, UnicodeDecodeError) as e:
                return {"error": f"Failed to decode plugin.json content: {str(e)}"}
            except json.JSONDecodeError as e:
                return {"error": f"Invalid JSON in plugin.json: {str(e)}"}
                
        except requests.exceptions.Timeout:
            return {"error": "Request timeout while fetching plugin.json"}
        except requests.exceptions.ConnectionError:
            return {"error": "Connection error while fetching plugin.json"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Unexpected error fetching plugin.json: {str(e)}"}
    
    def _fetch_plugin_image(self, owner: str, repo: str) -> Optional[bytes]:
        """
        Fetch plugin-icon.png from GitHub repository via Contents API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            bytes: Image data if found, None otherwise
        """
        try:
            url = f"{self.api_base}/repos/{owner}/{repo}/contents/plugin-icon.png"
            
            response = requests.get(url, timeout=self.timeout)
            
            if response.status_code == 404:
                # Image not found - this is acceptable
                return None
            elif response.status_code != 200:
                # Other errors - return None but could log if needed
                return None
            
            # Parse GitHub API response
            content_info = response.json()
            
            if content_info.get("type") != "file":
                return None
            
            # Decode base64 content
            if "content" not in content_info:
                return None
            
            try:
                image_bytes = base64.b64decode(content_info["content"])
                return image_bytes
            except base64.binascii.Error:
                return None
                
        except (requests.exceptions.RequestException, Exception):
            # Silently handle image fetch errors - images are optional
            return None
    
    def get_fallback_image_emoji(self) -> str:
        """
        Get fallback emoji for missing plugin images.
        
        Returns:
            str: Package emoji as fallback
        """
        return "📦"