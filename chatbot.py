"""
Chatbot with OpenAI + MirEye API Integration.

Uses OpenAI GPT-4o for general Q&A and integrates MirEye API
for geospatial queries about US locations via function calling.
MirEye is only called when the user's question is location-related.
"""

import json
import os
import sys

import requests
from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration — load from .env, never hardcoded
# ---------------------------------------------------------------------------

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MIREYE_API_TOKEN = os.getenv("MIREYE_API_TOKEN")

MIREYE_BASE_URL = "https://api.mireye.com"
MIREYE_TIMEOUT = 120  # MirEye docs recommend at least 120s for /v1/ask


def _check_keys() -> None:
    """Validate that required API keys are present."""
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not MIREYE_API_TOKEN:
        missing.append("MIREYE_API_TOKEN")
    if missing:
        print(
            f"[ERROR] Missing environment variable(s): {', '.join(missing)}\n"
            "Please set them in a .env file. See .env.example for reference."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# MirEye API helpers
# ---------------------------------------------------------------------------


def _mireye_headers() -> dict:
    """Return authorization headers for MirEye API calls."""
    return {
        "Authorization": f"Bearer {MIREYE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def mireye_ask(
    question: str,
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """
    Call MirEye POST /v1/ask — natural-language Q&A about a US location.

    Requires either (lat + lng) or address, never both.
    """
    payload: dict = {"question": question}

    if address:
        payload["address"] = address
    elif lat is not None and lng is not None:
        payload["lat"] = lat
        payload["lng"] = lng
    else:
        return {"error": "Either 'address' or both 'lat' and 'lng' must be provided."}

    try:
        resp = requests.post(
            f"{MIREYE_BASE_URL}/v1/ask",
            headers=_mireye_headers(),
            json=payload,
            timeout=MIREYE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "MirEye /v1/ask request timed out (120s). Try again later."}
    except requests.exceptions.HTTPError as exc:
        return {"error": f"MirEye /v1/ask HTTP error: {exc.response.status_code}", "detail": exc.response.text}
    except requests.exceptions.RequestException as exc:
        return {"error": f"MirEye /v1/ask request failed: {str(exc)}"}


def mireye_fetch(
    fields: list[str] | None = None,
    preset: str | None = None,
    address: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """
    Call MirEye POST /v1/fetch — deterministic per-field data retrieval.

    Requires either (lat + lng) or address, never both.
    Requires at least one of 'fields' or 'preset'.
    """
    payload: dict = {}

    if address:
        payload["address"] = address
    elif lat is not None and lng is not None:
        payload["lat"] = lat
        payload["lng"] = lng
    else:
        return {"error": "Either 'address' or both 'lat' and 'lng' must be provided."}

    if fields:
        payload["fields"] = fields
    if preset:
        payload["preset"] = preset

    if not fields and not preset:
        return {"error": "At least one of 'fields' or 'preset' must be provided."}

    try:
        resp = requests.post(
            f"{MIREYE_BASE_URL}/v1/fetch",
            headers=_mireye_headers(),
            json=payload,
            timeout=MIREYE_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "MirEye /v1/fetch request timed out (120s). Try again later."}
    except requests.exceptions.HTTPError as exc:
        return {"error": f"MirEye /v1/fetch HTTP error: {exc.response.status_code}", "detail": exc.response.text}
    except requests.exceptions.RequestException as exc:
        return {"error": f"MirEye /v1/fetch request failed: {str(exc)}"}


def mireye_geocode(address: str) -> dict:
    """
    Call MirEye POST /v1/geocode — resolve a US address or place name to coordinates.

    Use this to convert casual place names (e.g. "Times Square", "downtown Houston")
    into precise lat/lng coordinates before calling mireye_ask or mireye_fetch.
    """
    payload = {"address": address}

    try:
        resp = requests.post(
            f"{MIREYE_BASE_URL}/v1/geocode",
            headers=_mireye_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "MirEye /v1/geocode request timed out."}
    except requests.exceptions.HTTPError as exc:
        return {"error": f"MirEye /v1/geocode HTTP error: {exc.response.status_code}", "detail": exc.response.text}
    except requests.exceptions.RequestException as exc:
        return {"error": f"MirEye /v1/geocode request failed: {str(exc)}"}


# ---------------------------------------------------------------------------
# OpenAI tool definitions — these tell GPT when & how to call MirEye
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mireye_geocode",
            "description": (
                "Resolve any US place name, landmark, city, neighborhood, or address into "
                "precise lat/lng coordinates. Use this FIRST when the user mentions a location "
                "casually (e.g. 'Manhattan', 'Times Square', 'downtown Houston', 'near the Golden Gate Bridge') "
                "and you need coordinates to pass to mireye_ask or mireye_fetch. "
                "You can pass any descriptive location string — it doesn't have to be a full street address."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": (
                            "The location to geocode. Can be a full street address, a landmark, "
                            "a city name, a neighborhood, etc. (e.g. 'Times Square, New York, NY', "
                            "'1600 Pennsylvania Ave, Washington DC', 'Golden Gate Bridge, San Francisco')."
                        ),
                    },
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mireye_ask",
            "description": (
                "Ask a natural-language question about a specific US location. "
                "Use this when the user asks about flood risk, wildfire risk, zoning, "
                "land cover, environmental hazards, infrastructure, or any location-specific "
                "question about a place in the United States. "
                "The user does NOT need to provide coordinates — if they mention a place name, "
                "first use mireye_geocode to get coordinates, then pass lat+lng here. "
                "Alternatively you can pass an address string directly. "
                "Provide either an 'address' OR 'lat'+'lng', never both."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The natural-language question about the location.",
                    },
                    "address": {
                        "type": "string",
                        "description": "A US street address (e.g. '350 5th Ave, New York, NY 10118'). Use this OR lat/lng.",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude of the location (US coverage: 18–72).",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude of the location (US coverage: -180 to -65).",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mireye_fetch",
            "description": (
                "Fetch specific structured geospatial data fields for a US location. "
                "Use this when the user asks for specific data points like elevation, "
                "slope, flood zone status, NDVI, tree canopy percentage, etc. "
                "You can request individual fields by name or use a preset bundle. "
                "Available presets: terrain, flood_risk, wildfire_underwrite, land_cover, "
                "site_selection, building_lookup, points_of_interest, utilities, boundaries, "
                "solar_siting, wind_siting, storage_siting, data_center_siting, "
                "grid_interconnect, natural_hazard. "
                "The user does NOT need to provide coordinates — if they mention a place name, "
                "first use mireye_geocode to get coordinates, then pass lat+lng here. "
                "Provide either an 'address' OR 'lat'+'lng', never both."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of field names to retrieve (e.g. ['elevation', 'slope_degrees', "
                            "'coast_distance_m', 'within_floodplain_polygon'])."
                        ),
                    },
                    "preset": {
                        "type": "string",
                        "description": (
                            "A preset bundle name (e.g. 'terrain', 'flood_risk', 'wildfire_underwrite', "
                            "'land_cover', 'site_selection', 'building_lookup', 'points_of_interest', "
                            "'utilities', 'boundaries', 'solar_siting', 'wind_siting', "
                            "'storage_siting', 'data_center_siting', 'grid_interconnect', 'natural_hazard')."
                        ),
                    },
                    "address": {
                        "type": "string",
                        "description": "A US street address. Use this OR lat/lng.",
                    },
                    "lat": {
                        "type": "number",
                        "description": "Latitude of the location.",
                    },
                    "lng": {
                        "type": "number",
                        "description": "Longitude of the location.",
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher — executes MirEye calls when OpenAI requests them
# ---------------------------------------------------------------------------

TOOL_MAP = {
    "mireye_geocode": mireye_geocode,
    "mireye_ask": mireye_ask,
    "mireye_fetch": mireye_fetch,
}


def execute_tool_call(name: str, arguments: dict) -> str:
    """Run a tool function and return the result as a JSON string."""
    func = TOOL_MAP.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})

    result = func(**arguments)
    return json.dumps(result, indent=2, default=str)


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a helpful assistant that can answer general questions and also "
    "provide detailed geospatial information about US locations using the MirEye API.\n\n"
    "LOCATION HANDLING (AUTOMATIC CONVERSION):\n"
    "- Users will usually NOT enter coordinates. They will say things like 'in Central Park', 'Galveston, TX', 'Aspen, CO', '350 5th Ave, NY', or give a landmark/city name.\n"
    "- NEVER ask the user for coordinates.\n"
    "- When given a specific street address or landmark (e.g., '350 5th Ave, New York', 'Times Square', 'Galveston Island State Park'), pass it as `address` or geocode it with `mireye_geocode`.\n"
    "- If the user names a broad city/town without a street address (e.g., 'Galveston, Texas', 'Aspen, Colorado'), MirEye's address resolver may consider it too coarse. In that case, use your knowledge to provide the approximate center coordinates (`lat` and `lng`) of that city/place to `mireye_ask` or `mireye_fetch` (e.g., Galveston is 29.3013, -94.7977; Aspen is 39.1911, -106.8175; South Lake Tahoe is 38.9399, -119.9772).\n\n"
    "WHEN TO CALL MIREYE:\n"
    "- When a user asks about a US location — such as flood risk, wildfire risk, elevation, zoning, land cover, environmental data, infrastructure, soil conditions, nearby amenities, energy siting, or physical-world data — use MirEye tools (`mireye_geocode`, `mireye_ask`, `mireye_fetch`).\n"
    "- Use `mireye_ask` for open-ended natural-language questions about a location.\n"
    "- Use `mireye_fetch` when the user wants specific structured data fields or a preset bundle (e.g., 'terrain', 'flood_risk', 'wildfire_underwrite', 'utilities', etc.).\n"
    "- For all non-location questions (coding, math, general knowledge, greetings, etc.), answer directly WITHOUT calling any MirEye tools.\n\n"
    "OUTPUT FORMATTING:\n"
    "- When presenting MirEye data, clearly summarize the findings and mention the sources/citations provided in the response."
)


def run_chatbot() -> None:
    """Main chatbot loop."""
    _check_keys()

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Conversation history
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("=" * 60)
    print("  Chatbot — OpenAI + MirEye Integration")
    print("  Ask anything! Location questions use MirEye data.")
    print("  Type 'quit' or 'exit' to stop.")
    print("=" * 60)
    print()

    while True:
        # Get user input
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        # Add user message to history
        messages.append({"role": "user", "content": user_input})

        try:
            # Send to OpenAI with tools
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            assistant_message = response.choices[0].message

            # Handle tool calls (OpenAI wants to call MirEye)
            while assistant_message.tool_calls:
                # Add assistant's tool-call message to history
                messages.append(assistant_message.model_dump())

                # Execute each tool call
                for tool_call in assistant_message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    print(f"  [Calling MirEye: {func_name}...]")

                    result = execute_tool_call(func_name, func_args)

                    # Add tool result to conversation
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                # Get OpenAI's response after processing tool results
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                assistant_message = response.choices[0].message

            # We now have a final text response
            reply = assistant_message.content or "(No response)"
            messages.append({"role": "assistant", "content": reply})

            print(f"\nAssistant: {reply}\n")

        except Exception as exc:
            print(f"\n[ERROR] {exc}\n")
            # Remove the failed user message so conversation stays clean
            messages.pop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_chatbot()
