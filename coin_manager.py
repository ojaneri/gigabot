import json
import os

class CoinManager:
    def __init__(self, file_path="coins.json"):
        self.file_path = file_path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    return json.load(f)
            except:
                return {"valid": [], "invalid": []}
        return {"valid": [], "invalid": []}

    def _save(self):
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_invalid(self, symbol):
        return symbol in self.data.get("invalid", [])

    def mark_invalid(self, symbol):
        if "invalid" not in self.data: self.data["invalid"] = []
        if symbol not in self.data["invalid"]:
            self.data["invalid"].append(symbol)
            # Remove de valid se estiver lá
            if symbol in self.data.get("valid", []):
                self.data["valid"].remove(symbol)
            self._save()

    def mark_valid(self, symbol):
        if "valid" not in self.data: self.data["valid"] = []
        if symbol not in self.data["valid"]:
            self.data["valid"].append(symbol)
            # Remove de invalid se estiver lá
            if symbol in self.data.get("invalid", []):
                self.data["invalid"].remove(symbol)
            self._save()

coin_manager = CoinManager()
