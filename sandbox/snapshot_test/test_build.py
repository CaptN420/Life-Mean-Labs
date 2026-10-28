import json
import os
import shutil
from datetime import datetime
from typing import List, Dict

# --- MODULE 1 : LE LEARNING_BUS (La mémoire brute) ---
class LearningBus:
    def __init__(self):
        self.logs = []

    def record(self, event_type: str, content: str):
        self.logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "content": content
        })
        print(f"[LearningBus] Enregistré : {event_type}")

    def get_all_logs(self) -> List[dict]:
        return self.logs

    def clear(self):
        self.logs = []
        print("[LearningBus] Historique vidé pour la prochaine session.")

# --- MODULE 2 : LE VERSION_MANAGER (La structure) ---
class SnapshotVersionManager:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.snapshots_dir = os.path.join(base_path, "snapshots")
        self.active_file = os.path.join(self.snapshots_dir, "active_snap.json")
        os.makedirs(self.snapshots_dir, exist_ok=True)

    def _get_latest_version(self) -> tuple[int, int, str]:
        versions = []
        if not os.path.exists(self.snapshots_dir):
            return (1, 0, "a")
        for f in os.listdir(self.snapshots_dir):
            if f.startswith("snapv") and f.endswith(".json"):
                parts = f.replace("snapv", "").replace(".json", "").split(".")
                versions.append((int(parts[0]), int(parts[1]), parts[2]))
        if not versions: return (1, 0, "a")
        versions.sort(key=lambda x: (x[0], x[1], ord(x[2]) if isinstance(x[2], str) else x[2]))
        return versions[-1]

    def build_snapshot(self, data: dict, feedback_logs: List[str], change_type: str = "patch") -> str:
        curr_maj, curr_min, curr_pat = self._get_latest_version()
        
        if change_type == "major":
            new_maj, new_min, new_pat = curr_maj + 1, 0, "a"
        elif change_type == "minor":
            new_maj, new_min, new_pat = curr_maj, curr_min + 1, "a"
        else:
            new_maj, new_min = curr_maj, curr_min
            next_pat = chr(ord(curr_pat) + 1)
            if ord(next_pat) > ord('z'):
                new_min += 1
                new_pat = "a"
            else:
                new_pat = next_pat

        version_str = f"v{new_maj}.{new_min}.{new_pat}"
        filename = f"snapv{new_maj}.{new_min}.{new_pat}.json"
        filepath = os.path.join(self.snapshots_dir, filename)

        print(f"\n--- [BUILD_START] Type: {change_type.upper()} ---")
        for log in feedback_logs:
            print(f"[BUILD_TRACE] {log}")
        
        snapshot_content = {
            "version": version_str,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "build_notes": feedback_logs
        }
        
        with open(filepath, 'w') as f:
            json.dump(snapshot_content, f, indent=4)
        
        shutil.copy(filepath, self.active_file)
        print(f"--- [BUILD_COMPLETE] {version_str} est maintenant ACTIF ---")
        return version_str

    def rollback(self, version_str: str) -> bool:
        version_parts = version_str.replace("v", "").split(".")
        filename = f"snapv{version_parts[0]}.{version_parts[1]}.{version_parts[2]}.json"
        source = os.path.join(self.snapshots_dir, filename)
        
        if not os.path.exists(source):
            print(f"Error: Version {version_str} not found.")
            return False
        
        shutil.copy(source, self.active_file)
        print(f"--- [ROLLBACK_SUCCESS] Reverted to {version_str} ---")
        return True

# --- MODULE 3 : LE BATCH_PROCESSOR (Le lien entre les deux) ---
class BatchProcessor:
    def __init__(self, learning_bus: LearningBus, version_manager: SnapshotVersionManager):
        self.bus = learning_bus
        self.vm = version_manager

    def run_batch(self, change_type: str = "patch"):
        raw_logs = self.bus.get_all_logs()
        if not raw_logs:
            print("Aucune donnée dans le LearningBus pour construire un Batch.")
            return

        processed_data = {"acquis": []}
        build_feedback = []
        
        for entry in raw_logs:
            if "success" in entry['content'].lower() or "validé" in entry['content'].lower():
                processed_data["acquis"].append(entry['content'])
                build_feedback.append(f"Validation de l'acquis : {entry['content']}")
            else:
                build_feedback.append(f"Traitement de l'erreur : {entry['content']}")

        version = self.vm.build_snapshot(processed_data, build_feedback, change_type)
        self.bus.clear()
        print(f"\n[BATCH_COMPLETE] Snapshot {version} consolidé.")

# --- TEST DU SYSTÈME COMPLET ---
if __name__ == "__main__":
    # Path de la sandbox
    path = r"C:\Users\celes\Documents\Hermes-Workspace\Life_mean\sandbox\snapshot_test"
    
    bus = LearningBus()
    vm = SnapshotVersionManager(path)
    processor = BatchProcessor(bus, vm)

    # Simulation d'une session de travail
    bus.record("concept_understood", "Le Routeur de Décision est compris.")
    bus.record("test_passed", "Test de validation de la version v1.0a réussi.")
    bus.record("error_caught", "Tentative d'accès non autorisée bloquée par le Gatekeeper.")

    # Déclenchement du Batch
    processor.run_batch(change_type="patch")
