"""Project authenticated broker model lists into PAL catalogs. Reads JSON from disk."""

import argparse
import json
from pathlib import Path

CONF = Path(__file__).resolve().parents[1] / "conf"
VENDORS = {"openai": "openai", "google": "google", "anthropic": "anthropic", "xai": "x-ai"}
CHAT = "/v1/chat/completions"
RESPONSES = "/v1/responses"
# CheaperInference documents these as base model + reasoning.mode=pro, not separate wire IDs.
PRO_MODE_BASES = {"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"}
# Same model, different wire IDs in the two brokers' catalogs.
EQUIVALENTS = {
    "google/gemini-3-flash-preview": "gemini-3-flash",
    "x-ai/grok-4.20": "grok-4.20-reasoning",
}
PROJECT_ALIASES = {
    "grok-4.1-fast-reasoning": ["grok-4-1-fast", "grok-4-1-fast-reasoning", "grok-4.1-fast", "grok-4.1"],
    "grok-4.1-fast-non-reasoning": ["grok-4-1-fast-non-reasoning"],
    "glm-4.6": ["glm4.6"],
    "gpt-5.4": ["gpt-5-4"],
    "gpt-5.5-pro": ["gpt-5-5-pro"],
    "gemini-2.5-flash": ["gemini-flash", "flash-2.5"],
    "claude-opus-5": ["opus-5", "claude-opus"],
    "claude-sonnet-5": ["sonnet-5", "claude-sonnet"],
}


def rows(path):
    data = json.loads(path.read_text())
    data = data["data"] if isinstance(data, dict) else data
    if not isinstance(data, list) or not data:
        raise ValueError(f"Missing account catalog in {path}")
    ids = [row["id"] for row in data]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Duplicate remote IDs in {path}")
    return data


def aliases_by_model():
    aliases = {}
    # Native aliases take precedence on collisions with the older OpenRouter catalog.
    for filename in ["openrouter", "gemini", "openai", "xai"]:
        for model in json.loads((CONF / f"{filename}_models.json").read_text())["models"]:
            wire = model["model_name"]
            bare = wire.split("/")[-1]
            logical = EQUIVALENTS.get(wire, EQUIVALENTS.get(f"google/{bare}", bare))
            for alias in model.get("aliases", []):
                aliases[alias] = logical
    for name, extra in PROJECT_ALIASES.items():
        aliases.update(dict.fromkeys(extra, name))
    return aliases


def model_entry(wire, logical, namespace, context, output, params, features, aliases):
    names = {logical, wire.split("/")[-1], *[a for a, m in aliases.items() if m == logical]}
    if namespace:
        names.add(f"{namespace}/{logical}")
    for other_id, same in EQUIVALENTS.items():
        if same == logical:
            names.update([other_id, other_id.split("/")[-1]])
    if logical.startswith("claude-") and "." in logical:
        dashed = logical.replace(".", "-")
        names.update([dashed, f"anthropic/{dashed}"])
    names.discard(wire)
    return {
        "model_name": wire,
        "aliases": sorted(names),
        "context_window": context or 0,
        "max_output_tokens": output or 0,
        "supports_temperature": "temperature" in params and not logical.startswith(("gpt-5", "gpt-6", "claude-")),
        "supports_images": "image" in features,
        "max_image_size_mb": 4 if "image" in features else 0,
        "supports_extended_thinking": "reasoning" in params,
        "supports_function_calling": "tools" in params,
        "supports_json_mode": "response_format" in params,
    }


def compile_catalogs(ci_rows, router_rows):
    aliases = aliases_by_model()
    primary = []
    secondary = []
    previous_router = {m["model_name"] for m in json.loads((CONF / "openrouter_models.json").read_text())["models"]}
    legacy_namespaces = {
        wire.split("/", 1)[1]: wire.split("/", 1)[0] for wire in sorted(previous_router) if "/" in wire
    }
    for row in ci_rows:
        name = row["id"]
        namespace = VENDORS.get(row["owned_by"].lower()) or legacy_namespaces.get(name)
        if not namespace and name != "glm-4.6":
            continue
        endpoints = row.get("supported_endpoints", [])
        if row.get("type") != "text" or name.endswith("-batch") or not {CHAT, RESPONSES}.intersection(endpoints):
            continue
        endpoint = RESPONSES if row.get("endpoint") == RESPONSES or CHAT not in endpoints else CHAT
        entry = model_entry(
            name,
            name,
            namespace,
            row.get("context_length"),
            row.get("max_output_tokens"),
            row.get("supported_parameters", {}).get(endpoint, []),
            ["image"] if row["capabilities"]["vision"] else [],
            aliases,
        )
        if endpoint == RESPONSES:
            entry["use_openai_response_api"] = True
        primary.append(entry)
        if name in PRO_MODE_BASES and RESPONSES in endpoints:
            pro = name + "-pro"
            primary.append(
                {
                    **entry,
                    "model_name": pro,
                    "aliases": ["openai/" + pro],
                    "use_openai_response_api": True,
                    "pro_mode_base_model": name,
                }
            )
    for row in router_rows:
        wire = row["id"]
        namespace, _, bare = wire.partition("/")
        if namespace not in VENDORS.values() and wire not in previous_router:
            continue
        if ":" in wire or row["architecture"]["output_modalities"] != ["text"]:
            continue
        logical = EQUIVALENTS.get(wire, bare)
        secondary.append(
            model_entry(
                wire,
                logical,
                namespace,
                row.get("context_length"),
                row["top_provider"].get("max_completion_tokens"),
                row["supported_parameters"],
                row["architecture"]["input_modalities"],
                aliases,
            )
        )
    for entries in [primary, secondary]:
        if not all(any(n in entry["model_name"] for entry in entries) for n in ["gemini-", "claude-", "gpt-", "grok-"]):
            raise ValueError("Incomplete catalog for the four configured families")
        seen = {}
        for entry in entries:
            for alias in [entry["model_name"], *entry["aliases"]]:
                owner = seen.setdefault(alias.lower(), entry["model_name"])
                if owner != entry["model_name"]:
                    raise ValueError(f"Catalog alias {alias} names both {owner} and {entry['model_name']}")
        entries.sort(key=lambda entry: entry["model_name"])
    return primary, secondary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cheaperinference", type=Path)
    parser.add_argument("openrouter", type=Path)
    parser.add_argument("--output-dir", type=Path, default=CONF)
    args = parser.parse_args()
    primary, secondary = compile_catalogs(rows(args.cheaperinference), rows(args.openrouter))
    for filename, entries in [("cheaperinference_models.json", primary), ("openrouter_chat_models.json", secondary)]:
        dest = args.output_dir / filename
        dest.write_text(json.dumps({"models": entries}, indent=2) + "\n")
        print(f"{len(entries)} models in {filename}")


if __name__ == "__main__":
    main()
