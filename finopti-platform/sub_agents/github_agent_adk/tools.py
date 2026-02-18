"""
GitHub Agent Tools
"""
import logging
import json
from typing import Dict, Any, List
from mcp_client import GitHubMCPClient

logger = logging.getLogger(__name__)

async def _call_gh_tool(tool_name: str, args: dict, pat: str = None) -> Dict[str, Any]:
    try:
        async with GitHubMCPClient(token=pat) as client:
            return await client.call_tool(tool_name, args)
    except ValueError as ve:
        return {"success": False, "error": str(ve), "action_needed": "ask_user_for_pat"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def search_repositories(query: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_repositories", {"query": query}, github_pat)

async def list_repositories(github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_repositories", {}, github_pat)

async def get_file_contents(owner: str, repo: str, path: str, branch: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "path": path}
    if branch: args["branch"] = branch
    return await _call_gh_tool("get_file_contents", args, github_pat)

async def create_or_update_file(owner: str, repo: str, path: str, content: str, message: str, branch: str = None, sha: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "path": path, "content": content, "message": message}
    if branch: args["branch"] = branch
    if sha: args["sha"] = sha
    return await _call_gh_tool("create_or_update_file", args, github_pat)

async def push_files(owner: str, repo: str, branch: str, files: str, message: str, github_pat: str = None) -> Dict[str, Any]:
    """
    Push files to a branch.
    files: JSON string representing list of files [{'path': '...', 'content': '...'}, ...]
    """
    try:
         if isinstance(files, str):
             files_list = json.loads(files)
         else:
             files_list = files
    except:
         files_list = files # Fallback
         
    return await _call_gh_tool("push_files", {"owner": owner, "repo": repo, "branch": branch, "files": files_list, "message": message}, github_pat)

async def create_issue(owner: str, repo: str, title: str, body: str = None, github_pat: str = None) -> Dict[str, Any]:
    # [Fix] MCP Server uses "issue_write" with method="create"
    args = {"owner": owner, "repo": repo, "title": title, "method": "create"}
    if body: args["body"] = body
    return await _call_gh_tool("issue_write", args, github_pat)

async def list_issues(owner: str, repo: str, state: str = "open", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_issues", {"owner": owner, "repo": repo, "state": state}, github_pat)

async def update_issue(owner: str, repo: str, issue_number: int, title: str = None, body: str = None, state: str = None, github_pat: str = None) -> Dict[str, Any]:
    # [Fix] MCP Server uses "issue_write" with method="update"
    args = {"owner": owner, "repo": repo, "issue_number": issue_number, "method": "update"}
    if title: args["title"] = title
    if body: args["body"] = body
    if state: args["state"] = state
    return await _call_gh_tool("issue_write", args, github_pat)

async def add_issue_comment(owner: str, repo: str, issue_number: int, body: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("add_issue_comment", {"owner": owner, "repo": repo, "issue_number": issue_number, "body": body}, github_pat)

async def create_pull_request(owner: str, repo: str, title: str, head: str, base: str, body: str = None, github_pat: str = None) -> Dict[str, Any]:
    args = {"owner": owner, "repo": repo, "title": title, "head": head, "base": base}
    if body: args["body"] = body
    return await _call_gh_tool("create_pull_request", args, github_pat)

async def list_pull_requests(owner: str, repo: str, state: str = "open", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_pull_requests", {"owner": owner, "repo": repo, "state": state}, github_pat)

async def merge_pull_request(owner: str, repo: str, pull_number: int, merge_method: str = "merge", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("merge_pull_request", {"owner": owner, "repo": repo, "pull_number": pull_number, "merge_method": merge_method}, github_pat)

async def get_pull_request(owner: str, repo: str, pull_number: int, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("get_pull_request", {"owner": owner, "repo": repo, "pull_number": pull_number}, github_pat)

async def create_branch(owner: str, repo: str, branch: str, from_branch: str = "main", github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("create_branch", {"owner": owner, "repo": repo, "branch": branch, "from_branch": from_branch}, github_pat)

async def list_branches(owner: str, repo: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("list_branches", {"owner": owner, "repo": repo}, github_pat)

async def get_commit(owner: str, repo: str, ref: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("get_commit", {"owner": owner, "repo": repo, "ref": ref}, github_pat)

async def search_code(q: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_code", {"q": q}, github_pat)

async def search_issues(q: str, github_pat: str = None) -> Dict[str, Any]:
    return await _call_gh_tool("search_issues", {"q": q}, github_pat)
