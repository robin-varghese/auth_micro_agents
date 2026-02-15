"""
Storage Agent Tools
"""
import os
import asyncio
import logging
from typing import Dict, Any, List
from datetime import timedelta
from google.cloud import storage
from mcp_client import ensure_mcp

logger = logging.getLogger(__name__)

async def list_objects(bucket_name: str, prefix: str = "") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_objects", {"bucket_name": bucket_name, "prefix": prefix})

async def read_object_metadata(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_object_metadata", {"bucket_name": bucket_name, "object_name": object_name})

async def read_object_content(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("read_object_content", {"bucket_name": bucket_name, "object_name": object_name})

async def delete_object(bucket_name: str, object_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("delete_object", {"bucket_name": bucket_name, "object_name": object_name})

async def write_object(bucket_name: str, object_name: str, content: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    # 1. Write the object via MCP
    res = await client.call_tool("write_object_safe", {"bucket_name": bucket_name, "object_name": object_name, "content": content})
    if "error" in res:
        return res
    
    # 2. Generate Signed URL for immediate access
    try:
        def _get_signed_url():
             storage_client = storage.Client()
             bucket = storage_client.bucket(bucket_name)
             blob = bucket.blob(object_name)
             try:
                 return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
             except:
                 return f"https://storage.cloud.google.com/{bucket_name}/{object_name}"
        
        signed_url = await asyncio.to_thread(_get_signed_url)
        return {
            "result": f"Object '{object_name}' written to bucket '{bucket_name}'.",
            "gcs_uri": f"gs://{bucket_name}/{object_name}",
            "signed_url": signed_url
        }
    except Exception as e:
        return {"result": f"Object written, but signed URL failed: {e}", "gcs_uri": f"gs://{bucket_name}/{object_name}"}

async def update_object_metadata(bucket_name: str, object_name: str, metadata: dict) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("update_object_metadata", {"bucket_name": bucket_name, "object_name": object_name, "metadata": metadata})

async def copy_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("copy_object_safe", {"source_bucket_name": source_bucket, "source_object_name": source_object, "destination_bucket_name": dest_bucket, "destination_object_name": dest_object})

async def move_object(source_bucket: str, source_object: str, dest_bucket: str, dest_object: str) -> Dict[str, Any]:
    # MCP does not support move_object directly. Implementing as copy + delete.
    client = await ensure_mcp()
    copy_res = await client.call_tool("copy_object_safe", {"source_bucket_name": source_bucket, "source_object_name": source_object, "destination_bucket_name": dest_bucket, "destination_object_name": dest_object})
    if "error" in copy_res:
        return copy_res
    return await client.call_tool("delete_object", {"bucket_name": source_bucket, "object_name": source_object})

async def upload_object(bucket_name: str, object_name: str, file_path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("upload_object_safe", {"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path})

async def download_object(bucket_name: str, object_name: str, file_path: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("download_object", {"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path})

async def list_buckets() -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_buckets", {})

async def create_bucket(bucket_name: str, location: str = "US") -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("create_bucket", {"bucket_name": bucket_name, "location": location})

async def delete_bucket(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("delete_bucket", {"bucket_name": bucket_name})

async def get_bucket_metadata(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_bucket_metadata", {"bucket_name": bucket_name})

async def update_bucket_labels(bucket_name: str, labels: dict) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("update_bucket_labels", {"bucket_name": bucket_name, "labels": labels})

async def get_bucket_location(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_bucket_location", {"bucket_name": bucket_name})

async def view_iam_policy(bucket_name: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("view_iam_policy", {"bucket_name": bucket_name})

async def check_iam_permissions(bucket_name: str, permissions: List[str]) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("check_iam_permissions", {"bucket_name": bucket_name, "permissions": permissions})

async def get_metadata_table_schema(config_name: str, project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("get_metadata_table_schema", {"config_name": config_name, "project": project})

async def execute_insights_query(query: str, project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("execute_insights_query", {"query": query, "project": project})

async def list_insights_configs(project: str) -> Dict[str, Any]:
    client = await ensure_mcp()
    return await client.call_tool("list_insights_configs", {"project": project})

async def upload_file_from_local(bucket_name: str, source_file_path: str, destination_blob_name: str) -> Dict[str, Any]:
    """Uploads a file from the local filesystem to GCS and returns a Signed URL."""
    try:
        if not os.path.exists(source_file_path):
             return {"error": f"Source file not found: {source_file_path}"}
        
        def _upload_and_sign():
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_path)
            
            try:
                # Use v4 signing
                return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
            except:
                # Fallback to Console URL (requires login)
                return f"https://storage.cloud.google.com/{bucket_name}/{destination_blob_name}"

        signed_url = await asyncio.to_thread(_upload_and_sign)
        gcs_uri = f"gs://{bucket_name}/{destination_blob_name}"
        
        return {
            "result": f"Successfully uploaded {source_file_path} to {gcs_uri}.",
            "gcs_uri": gcs_uri,
            "signed_url": signed_url
        }
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        return {"error": str(e)}
