Lets replace the mock MCP servers with the actual ones. The new MCP servers and Agents should fit into the current architecture using the APISIX API gateway and OPA for authorization.

1. Build the MCP Servers
Build the correct Gcloud MCP server from scratch and deploy it in the local Docker Desktop -> (https://github.com/robin-varghese/gcloud-mcpserver/blob/0c1a64dbfc22d793258e5f6d0cfb7584e1fa8f9e/remote-mcp-server/gcloud-mcp-server/gcloud_mcp_strategy.md)
Docker file to build Gcloud MCP server is available in https://github.com/robin-varghese/gcloud-mcpserver/blob/0c1a64dbfc22d793258e5f6d0cfb7584e1fa8f9e/remote-mcp-server/gcloud-mcp-server/Dockerfile 

Strategy: Google Cloud Monitoring MCP Server in Docker ->https://github.com/robin-varghese/gcloud-mcpserver/blob/0c1a64dbfc22d793258e5f6d0cfb7584e1fa8f9e/remote-mcp-server/gcloud-monitoring-mcp/gcloud_monitoring_mcp_strategy.md
Docker file to build Gcloud Monitoring MCP server is available in https://github.com/robin-varghese/gcloud-mcpserver/blob/0c1a64dbfc22d793258e5f6d0cfb7584e1fa8f9e/remote-mcp-server/gcloud-monitoring-mcp/Dockerfile

2. Build the MCP Agents
Now build the Gcloud MCP Agent and Monitoring MCP Agent using the below strategy
There should be an Gcloud MCP agent (client) working using the above Gcloud MCP server. The code is already available in the project folder /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mcp_servers/external/gcloud-mcp-server

There should be an Monitoring MCP agent (client) working using the above Monitoring MCP server. The code is already available in the project folder /Users/robinkv/dev_workplace/all_codebase/auth_micro_agents/finopti-platform/mcp_servers/external/gcloud-monitoring-mcp-server

3. Deployment of MCP servers and agents
After both MCP servers and the agents are built, push the images to the local Docker Desktop 

4. Testing of MCP servers and agents
Add/update new/existing test scripts into the test suit
test the new MCP servers and agents by running the test suit

5. Documentation of MCP servers and agents
Update the documentation of MCP servers and agents

6. Cleanup
Remove the mock MCP servers and agents from the project
Remove the files are folders of mock MCP servers and agents from the project
