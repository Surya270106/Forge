from forgebench import parse_port


def build_server_config(port_text: str) -> dict:
    return {"port": parse_port(port_text), "host": "127.0.0.1"}
