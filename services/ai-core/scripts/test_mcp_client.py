import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


MCP_URL = "http://127.0.0.1:8000/mcp/"


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("MCP连接成功")
            print("可用工具:", [tool.name for tool in tools.tools])

            resources = await session.list_resources()
            print("Available resources:", [str(item.uri) for item in resources.resources])

            catalog = await session.read_resource("commerce://data-catalog")
            print("Data catalog resource:")
            for content in catalog.contents:
                if hasattr(content, "text"):
                    print(content.text)

            prompts = await session.list_prompts()
            print("Available prompts:", [item.name for item in prompts.prompts])

            prompt = await session.get_prompt(
                "presales_assistant",
                arguments={"customer_question": "请查询商品 P1002 的库存"},
            )
            print("Presales prompt:")
            for message in prompt.messages:
                if hasattr(message.content, "text"):
                    print(message.content.text)

            result = await session.call_tool(
                "check_inventory",
                arguments={"product_id": "P1002"},
            )
            print("P1002库存工具返回:")
            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
