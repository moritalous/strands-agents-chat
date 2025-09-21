import asyncio
import json
import os
import time
from contextlib import ExitStack
from datetime import datetime
from functools import partial

import nest_asyncio
import streamlit as st
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from strands.agent import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.tools.mcp import MCPClient

nest_asyncio.apply()

storage_dir = "sessions"
agent_id = "default"


class MCPManager:
    def __init__(self, config_file="mcp.json"):
        self.config_file = config_file

    def load_config(self):
        with open(self.config_file, mode="rt", encoding="utf-8") as f:
            return json.load(f)["mcpServers"]

    def save_config(self, mcp_servers: dict):
        with open(self.config_file, mode="wt", encoding="utf-8") as f:
            json.dump({"mcpServers": mcp_servers}, f, ensure_ascii=False, indent=2)

    def get_clients(self) -> list[MCPClient]:
        mcp_servers = self.load_config()
        clients = []

        for name, config in mcp_servers.items():
            if config.get("disabled", False):
                continue

            if "url" in config:
                clients.append(
                    MCPClient(partial(streamablehttp_client, url=config.get("url")))
                )
            else:
                clients.append(
                    MCPClient(
                        partial(
                            stdio_client,
                            StdioServerParameters(
                                command=config.get("command", ""),
                                args=config.get("args", []),
                                env=config.get("env", {}),
                            ),
                        )
                    )
                )
        return clients

    def update_disabled(self, name: str, disabled: bool):
        config = self.load_config()
        config[name]["disabled"] = disabled
        self.save_config(config)


class ModelManager:
    def __init__(self, config_file="model_config.json"):
        self.config_file = config_file

    def load_config(self):
        with open(self.config_file, mode="rt", encoding="utf-8") as f:
            config = json.load(f)
        return config["select"], config["models"]

    def save_config(self, select_model: str, models: dict):
        with open(self.config_file, mode="wt", encoding="utf-8") as f:
            json.dump(
                {"select": select_model, "models": models},
                f,
                ensure_ascii=False,
                indent=2,
            )

    def update_selected(self):
        _, models = self.load_config()
        self.save_config(st.session_state.select_model, models)


class SessionManager:
    def __init__(self, storage_dir="sessions"):
        self.storage_dir = storage_dir

    def get_session_id_list(self):
        session_list = []
        if os.path.exists(self.storage_dir) and os.path.isdir(self.storage_dir):
            for item in os.listdir(self.storage_dir):
                item_path = os.path.join(self.storage_dir, item)
                if os.path.isdir(item_path) and item.startswith("session_"):
                    try:
                        session_id = item[len("session_") :]
                        session_list.append(session_id)
                    except ValueError:
                        continue
        return sorted(session_list, reverse=True)

    def format_time(self, session_id: str):
        timestamp = int(session_id)
        dt_local = datetime.fromtimestamp(timestamp)
        return dt_local.strftime("%Y/%m/%d %H:%M")

    def set_session_id(self, session_id: str):
        st.session_state.session_id = session_id


class MessageRenderer:
    def __init__(self, storage_dir="sessions", agent_id="default"):
        self.storage_dir = storage_dir
        self.agent_id = agent_id

    def write_message(self, message):
        with st.chat_message(message["role"]):
            for content in message["content"]:
                if "text" in content:
                    st.write(content["text"])
                if "toolUse" in content:
                    with st.expander(
                        f"toolUse: {content['toolUse']['name']}", expanded=True
                    ):
                        st.write(content["toolUse"])
                if "toolResult" in content:
                    with st.expander("toolResult", expanded=False):
                        st.write(content["toolResult"])
                if "reasoningContent" in content:
                    with st.expander("reasoningContent", expanded=False):
                        st.write(content["reasoningContent"])

    def write_past_messages(self):
        try:
            session_manager_instance = FileSessionManager(
                session_id=st.session_state.session_id,
                storage_dir=self.storage_dir,
            )
            messages = session_manager_instance.list_messages(
                session_id=st.session_state.session_id,
                agent_id=self.agent_id,
            )

            for m in messages:
                self.write_message(m.message)
        except Exception:
            pass


# インスタンス作成
mcp_manager = MCPManager()
model_manager = ModelManager()
session_manager = SessionManager(storage_dir)
message_renderer = MessageRenderer(storage_dir, agent_id)


async def main():
    st.title("Strands Angets Chat")

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(int(time.time()))

    with st.sidebar:
        # select_model, models
        st.subheader("Model")
        select_model, models = model_manager.load_config()
        selected_model = st.selectbox(
            "Model",
            options=models.keys(),
            index=list(models.keys()).index(select_model),
            on_change=model_manager.update_selected,
            key="select_model",
            label_visibility="collapsed",
        )

        st.divider()
        st.subheader("MCP tools")

        for k, v in mcp_manager.load_config().items():
            disabled = not v.get("disabled", False)
            st.checkbox(
                k,
                value=disabled,
                on_change=mcp_manager.update_disabled,
                args=[k, disabled],
            )

    if st.session_state.session_id in session_manager.get_session_id_list():
        message_renderer.write_past_messages()

    if prompt := st.chat_input():
        with st.chat_message("user"):
            st.write(prompt)

        with ExitStack() as stack:
            tools = []
            for client in mcp_manager.get_clients():
                stack.enter_context(client)
                tools.extend(client.list_tools_sync())

            agent = Agent(
                model=BedrockModel(**models[selected_model]),
                tools=tools,
                callback_handler=None,
                conversation_manager=SlidingWindowConversationManager(window_size=9999),
                session_manager=FileSessionManager(
                    session_id=st.session_state.session_id,
                    storage_dir=storage_dir,
                ),
            )

            agent_stream = agent.stream_async(prompt)
            async for event in agent_stream:
                if "message" in event:
                    message_renderer.write_message(event["message"])

    with st.sidebar:
        st.divider()
        st.button(
            "New thread",
            width="stretch",
            on_click=session_manager.set_session_id,
            args=[str(int(time.time()))],
            type="primary",
        )
        for session_id in session_manager.get_session_id_list():
            st.button(
                session_manager.format_time(session_id),
                width="stretch",
                on_click=session_manager.set_session_id,
                args=[session_id],
                key=session_id,
            )


asyncio.run(main=main())
