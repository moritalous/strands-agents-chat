# Strands Agents Chat

A chat application using Strands Agents and Streamlit. Uses Amazon Bedrock as the LLM provider. Supports adding arbitrary MCP servers through configuration (supports both stdio and streamable HTTP).

## Key Features

- Model Selection: By default, open weight models provided by Amazon Bedrock are available. Amazon Nova and Anthropic Claude can also be enabled by modifying the configuration file
- MCP Functionality: MCP servers can be added through configuration files. You can also enable/disable MCP servers as needed
- Message Management: Message history is saved to files for persistence
- Thread Management: Messages are managed in multiple thread units. You can select past threads to continue conversations

## Usage

1. Clone the source code from GitHub

    ```shell
    git clone https://github.com/moritalous/strands-agents-chat.git
    cd strands-agents-chat
    ```

2. Copy the sample configuration files for models and MCP

    ```shell
    cp model_config.json.sample model_config.json
    cp mcp.json.sample mcp.json
    ```

3. Edit the model and MCP configuration files as needed

4. Launch the application

    ```shell
    uv run streamlit run app.py
    ```

## License

MIT License

