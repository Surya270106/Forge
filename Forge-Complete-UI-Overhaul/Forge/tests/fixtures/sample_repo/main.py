class ConfigManager:
    """Manages application configuration."""

    def __init__(self):
        self.config = {}

    def load(self, path: str):
        pass


def main():
    manager = ConfigManager()
    manager.load("config.json")
    print("Started")


if __name__ == "__main__":
    main()
