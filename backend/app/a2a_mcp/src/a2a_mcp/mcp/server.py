# type: ignore
import json
import os
import sqlite3
import traceback
import zipfile
import io
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
import numpy as np
import pandas as pd
import requests
import tempfile
from ..mcp_config import mcp_settings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.logging import get_logger
import psycopg2

logger = get_logger(__name__)
# Calculate the path to agent_cards directory relative to this file
AGENT_CARDS_DIR = Path(__file__).parent.parent.parent.parent / "agent_cards"
MODEL = "models/embedding-001"
SQLLITE_DB = (
    Path(__file__).parent.parent.parent.parent.parent.parent / "travel_agency.db"
)
PLACES_API_URL = "https://places.googleapis.com/v1/places:searchText"
ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".c", ".cpp", ".js"}  # Customize this list


def init_api_key():
    """Initialize the API key for Google Generative AI."""
    if not mcp_settings.GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY is not set")
        raise ValueError("GOOGLE_API_KEY is not set")

    genai.configure(api_key=mcp_settings.GOOGLE_API_KEY)


def generate_embeddings(text):
    """Generates embeddings for the given text using Google Generative AI.

    Args:
        text: The input string for which to generate embeddings.

    Returns:
        A list of embeddings representing the input text.
    """
    return genai.embed_content(
        model=MODEL,
        content=text,
        task_type="retrieval_document",
    )["embedding"]


def load_agent_cards():
    """Loads agent card data from JSON files within a specified directory.

    Returns:
        A list containing JSON data from an agent card file found in the specified directory.
        Returns an empty list if the directory is empty, contains no '.json' files,
        or if all '.json' files encounter errors during processing.
    """
    card_uris = []
    agent_cards = []
    dir_path = Path(AGENT_CARDS_DIR)
    if not dir_path.is_dir():
        logger.error(
            f"Agent cards directory not found or is not a directory: {AGENT_CARDS_DIR}"
        )
        return card_uris, agent_cards

    logger.info(f"Loading agent cards from card repo: {AGENT_CARDS_DIR}")

    for filename in os.listdir(AGENT_CARDS_DIR):
        if filename.lower().endswith(".json"):
            file_path = dir_path / filename

            if file_path.is_file():
                logger.info(f"Reading file: {filename}")
                try:
                    with file_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        logger.debug(f"Loaded agent card from {filename}: {type(data)}")
                        logger.debug(f"Agent card data: {data}")
                        card_uris.append(
                            f"resource://agent_cards/{Path(filename).stem}"
                        )
                        agent_cards.append(data)
                except json.JSONDecodeError as jde:
                    logger.error(f"JSON Decoder Error {jde}")
                except OSError as e:
                    logger.error(f"Error reading file {filename}: {e}.")
                except Exception as e:
                    logger.error(
                        f"An unexpected error occurred processing {filename}: {e}",
                        exc_info=True,
                    )
    logger.info(f"Finished loading agent cards. Found {len(agent_cards)} cards.")
    return card_uris, agent_cards


def build_agent_card_embeddings() -> pd.DataFrame:
    """Loads agent cards, generates embeddings for them, and returns a DataFrame.

    Returns:
        pd.DataFrame: A Pandas DataFrame containing the original
        'agent_card' data and their corresponding 'Embeddings'. Returns an empty
        DataFrame if no agent cards were loaded initially or if an exception occurred
        during the embedding generation process.
    """
    card_uris, agent_cards = load_agent_cards()
    logger.info("Generating Embeddings for agent cards")
    try:
        if agent_cards:
            df = pd.DataFrame({"card_uri": card_uris, "agent_card": agent_cards})
            df["card_embeddings"] = df.apply(
                lambda row: generate_embeddings(json.dumps(row["agent_card"])),
                axis=1,
            )
            logger.info("Done generating embeddings for agent cards")
            return df
        else:
            logger.warning("No agent cards loaded, returning empty DataFrame")
            return pd.DataFrame()
    except Exception as e:
        logger.error(f"An unexpected error occurred : {e}.", exc_info=True)
        return pd.DataFrame()


def serve(host, port, transport):  # noqa: PLR0915
    """Initializes and runs the Agent Cards MCP server.

    Args:
        host: The hostname or IP address to bind the server to.
        port: The port number to bind the server to.
        transport: The transport mechanism for the MCP server (e.g., 'stdio', 'sse').

    Raises:
        ValueError: If the 'GOOGLE_API_KEY' environment variable is not set.
    """
    init_api_key()
    logger.info("Starting Agent Cards MCP Server")
    mcp = FastMCP("agent-cards", host=host, port=port)

    df = build_agent_card_embeddings()

    @mcp.tool(
        name="find_agent",
        description="Finds the most relevant agent card based on a natural language query string.",
    )
    def find_agent(query: str) -> str:
        """Finds the most relevant agent card based on a query string.

        This function takes a user query, typically a natural language question or a task generated by an agent,
        generates its embedding, and compares it against the
        pre-computed embeddings of the loaded agent cards. It uses the dot
        product to measure similarity and identifies the agent card with the
        highest similarity score.

        Args:
            query: The natural language query string used to search for a
                   relevant agent.

        Returns:
            The json representing the agent card deemed most relevant
            to the input query based on embedding similarity.
        """
        logger.info(f"find_agent called with query: {query}")

        try:
            if df is None or df.empty:
                logger.error("No agent cards loaded")
                return json.dumps({"error": "No agent cards available"})

            query_embedding = genai.embed_content(
                model=MODEL, content=query, task_type="retrieval_query"
            )
            dot_products = np.dot(
                np.stack(df["card_embeddings"]), query_embedding["embedding"]
            )
            best_match_index = np.argmax(dot_products)
            logger.debug(
                f"Found best match at index {best_match_index} with score {dot_products[best_match_index]}"
            )

            # Return the agent card as a JSON string
            agent_card = df.iloc[best_match_index]["agent_card"]
            logger.debug(f"Agent card type: {type(agent_card)}")
            logger.debug(f"Agent card content: {agent_card}")

            # Ensure we return a proper JSON string with robust serialization
            try:
                if isinstance(agent_card, dict):
                    # Use a custom JSON encoder that handles non-serializable objects
                    json_result = json.dumps(
                        agent_card, default=str, ensure_ascii=False
                    )
                    logger.debug(f"JSON result: {json_result}")
                    return json_result
                elif isinstance(agent_card, str):
                    # If it's already a string, check if it's valid JSON
                    try:
                        json.loads(agent_card)  # Validate it's valid JSON
                        return agent_card
                    except json.JSONDecodeError:
                        # If not valid JSON, wrap it
                        return json.dumps({"content": agent_card}, default=str)
                else:
                    # For other types, convert to string and wrap
                    return json.dumps({"content": str(agent_card)}, default=str)
            except Exception as serialize_error:
                logger.error(f"JSON serialization error: {serialize_error}")
                return json.dumps(
                    {"error": f"Serialization failed: {str(serialize_error)}"},
                    default=str,
                )
        except Exception as e:
            logger.error(f"Error in find_agent: {e}")
            return json.dumps({"error": f"Failed to find agent: {str(e)}"})

    @mcp.tool()
    def query_places_data(query: str):
        """Query Google Places."""
        logger.info(f"Search for places : {query}")

        # Return dummy places data instead of calling Google Places API
        dummy_places = {
            "places": [
                {
                    "id": "place_1",
                    "displayName": {"text": "Heathrow Airport", "languageCode": "en"},
                    "formattedAddress": "London TW6, UK",
                },
                {
                    "id": "place_2",
                    "displayName": {"text": "Tower of London", "languageCode": "en"},
                    "formattedAddress": "London EC3N 4AB, UK",
                },
                {
                    "id": "place_3",
                    "displayName": {"text": "London Bridge", "languageCode": "en"},
                    "formattedAddress": "London Bridge, London, UK",
                },
                {
                    "id": "place_4",
                    "displayName": {"text": "Big Ben", "languageCode": "en"},
                    "formattedAddress": "Westminster, London SW1A 0AA, UK",
                },
                {
                    "id": "place_5",
                    "displayName": {"text": "British Museum", "languageCode": "en"},
                    "formattedAddress": "Great Russell St, Bloomsbury, London WC1B 3DG, UK",
                },
            ]
        }

        # Filter places based on query if needed
        query_lower = query.lower()
        if "airport" in query_lower:
            return {"places": [dummy_places["places"][0]]}  # Return Heathrow
        elif "museum" in query_lower:
            return {"places": [dummy_places["places"][4]]}  # Return British Museum
        elif "bridge" in query_lower:
            return {"places": [dummy_places["places"][2]]}  # Return London Bridge

        # Return all places by default
        return dummy_places

    @mcp.tool()
    def search_flights(
        departure_airport: str, arrival_airport: str, start_date: str, end_date: str
    ):
        """Search for flights with specific parameters."""
        logger.info(
            f"Search flights: {departure_airport} to {arrival_airport}, {start_date} to {end_date}"
        )

        # Return dummy flight search results
        dummy_flight_results = [
            {
                "id": 1,
                "carrier": "British Airways",
                "flight_number": "BA287",
                "departure_airport": departure_airport,
                "arrival_airport": arrival_airport,
                "departure_date": start_date,
                "departure_time": "10:30",
                "arrival_time": "22:45",
                "ticket_class": "ECONOMY",
                "price": 850.00,
                "duration": "11h 15m",
            },
            {
                "id": 2,
                "carrier": "Virgin Atlantic",
                "flight_number": "VS19",
                "departure_airport": departure_airport,
                "arrival_airport": arrival_airport,
                "departure_date": start_date,
                "departure_time": "14:20",
                "arrival_time": "02:35+1",
                "ticket_class": "BUSINESS",
                "price": 2400.00,
                "duration": "11h 15m",
            },
        ]

        return {"flights": dummy_flight_results}

    @mcp.tool()
    def search_hotels(location: str, check_in_date: str, check_out_date: str):
        """Search for hotels with specific parameters."""
        logger.info(f"Search hotels: {location}, {check_in_date} to {check_out_date}")

        # Return dummy hotel search results
        dummy_hotel_results = [
            {
                "id": 1,
                "name": "The Langham London",
                "location": location,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "room_type": "SUITE",
                "hotel_type": "LUXURY",
                "price_per_night": 450.00,
                "total_price": 1350.00,  # 3 nights
                "amenities": ["WiFi", "Spa", "Fitness Center", "Restaurant"],
                "rating": 4.8,
            },
            {
                "id": 2,
                "name": "Premier Inn London",
                "location": location,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "room_type": "STANDARD",
                "hotel_type": "BUDGET",
                "price_per_night": 120.00,
                "total_price": 360.00,  # 3 nights
                "amenities": ["WiFi", "Restaurant"],
                "rating": 4.2,
            },
        ]

        return {"hotels": dummy_hotel_results}

    @mcp.tool()
    def query_travel_data(query: str) -> dict:
        """ "name": "query_travel_data",
        "description": "Retrieves the most up-to-date, ariline, hotel and car rental availability. Helps with the booking.
        This tool should be used when a user asks for the airline ticket booking, hotel or accommodation booking, or car rental reservations.",
        "parameters": {
            "type": "object",
            "properties": {
            "query": {
                "type": "string",
                "description": "A SQL to run against the travel database."
            }
            },
            "required": ["query"]
        }
        """
        # Return dummy data instead of querying real database
        logger.info(f"Query received: {query}")

        # Parse the query to determine what type of data to return
        query_lower = query.lower()

        if "flights" in query_lower:
            # Return dummy flight data
            dummy_flights = [
                {
                    "id": 1,
                    "carrier": "British Airways",
                    "flight_number": 287,
                    "from_airport": "SFO",
                    "to_airport": "LHR",
                    "ticket_class": "BUSINESS",
                    "price": 2500.00,
                },
                {
                    "id": 2,
                    "carrier": "Virgin Atlantic",
                    "flight_number": 19,
                    "from_airport": "SFO",
                    "to_airport": "LHR",
                    "ticket_class": "ECONOMY",
                    "price": 800.00,
                },
                {
                    "id": 3,
                    "carrier": "British Airways",
                    "flight_number": 286,
                    "from_airport": "LHR",
                    "to_airport": "SFO",
                    "ticket_class": "BUSINESS",
                    "price": 2500.00,
                },
                {
                    "id": 4,
                    "carrier": "Virgin Atlantic",
                    "flight_number": 20,
                    "from_airport": "LHR",
                    "to_airport": "SFO",
                    "ticket_class": "ECONOMY",
                    "price": 800.00,
                },
            ]

            # Filter based on query parameters if possible
            if "business" in query_lower:
                result_flights = [
                    f for f in dummy_flights if f["ticket_class"] == "BUSINESS"
                ]
            elif "economy" in query_lower:
                result_flights = [
                    f for f in dummy_flights if f["ticket_class"] == "ECONOMY"
                ]
            else:
                result_flights = dummy_flights[:2]  # Return first 2 by default

            return json.dumps({"results": result_flights})

        elif "hotels" in query_lower:
            # Return dummy hotel data
            dummy_hotels = [
                {
                    "id": 1,
                    "name": "The Langham London",
                    "city": "London",
                    "hotel_type": "HOTEL",
                    "room_type": "SUITE",
                    "price_per_night": 450.00,
                },
                {
                    "id": 2,
                    "name": "Premier Inn London",
                    "city": "London",
                    "hotel_type": "HOTEL",
                    "room_type": "STANDARD",
                    "price_per_night": 120.00,
                },
                {
                    "id": 3,
                    "name": "Cozy London Flat",
                    "city": "London",
                    "hotel_type": "AIRBNB",
                    "room_type": "DOUBLE",
                    "price_per_night": 85.00,
                },
            ]

            # Filter based on query parameters
            if "suite" in query_lower:
                result_hotels = [h for h in dummy_hotels if h["room_type"] == "SUITE"]
            elif "airbnb" in query_lower:
                result_hotels = [h for h in dummy_hotels if h["hotel_type"] == "AIRBNB"]
            else:
                result_hotels = dummy_hotels[:2]  # Return first 2 by default

            return json.dumps({"results": result_hotels})

        elif "rental_cars" in query_lower or "cars" in query_lower:
            # Return dummy car rental data
            dummy_cars = [
                {
                    "id": 1,
                    "provider": "Hertz",
                    "city": "London",
                    "type_of_car": "SEDAN",
                    "daily_rate": 65.00,
                },
                {
                    "id": 2,
                    "provider": "Enterprise",
                    "city": "London",
                    "type_of_car": "SUV",
                    "daily_rate": 85.00,
                },
                {
                    "id": 3,
                    "provider": "Budget",
                    "city": "London",
                    "type_of_car": "TRUCK",
                    "daily_rate": 95.00,
                },
            ]

            # Filter based on query parameters
            if "suv" in query_lower:
                result_cars = [c for c in dummy_cars if c["type_of_car"] == "SUV"]
            elif "sedan" in query_lower:
                result_cars = [c for c in dummy_cars if c["type_of_car"] == "SEDAN"]
            else:
                result_cars = dummy_cars[:2]  # Return first 2 by default

            return json.dumps({"results": result_cars})

        # Default empty result
        return json.dumps({"results": []})

    @mcp.tool()
    def get_embeddings(text: str) -> dict:
        """Generate embeddings using Google Generative AI"""
        return genai.embed_content(
            model=MODEL,
            content=text,
            task_type="retrieval_document",
        )["embedding"]

    @mcp.tool()
    def download_repo_as_zip(github_url: str) -> zipfile.ZipFile:
        """Download GitHub repo as a ZIP archive"""

        owner_repo = github_url.rstrip("/").split("github.com/")[-1]
        zip_url = f"https://github.com/{owner_repo}/archive/refs/heads/master.zip"
        response = requests.get(zip_url)
        if response.status_code != 200:
            # fallback to main branch
            zip_url = f"https://github.com/{owner_repo}/archive/refs/heads/main.zip"
            response = requests.get(zip_url)
            if response.status_code != 200:
                raise Exception("Could not download repository ZIP.")
        return zipfile.ZipFile(io.BytesIO(response.content))

    @mcp.tool()
    def save_repo_to_vector_db(zip_file: zipfile.ZipFile) -> str:
        """Save repository content to a vector database."""
        try:
            conn = psycopg2.connect(
                dbname="your_db_name",
                user="your_user",
                password="your_password",
                host="your-db-name.internal",  # or "localhost" with proxy
                port=5432,
                sslmode="require",
            )
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS repo_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT,
                    content TEXT,
                    embedding BLOB
                )
                """
            )

            for file_info in zip_file.infolist():
                if not file_info.is_dir() and file_info.filename.endswith(".py"):
                    with zip_file.open(file_info) as f:
                        content = f.read().decode("utf-8")
                        embedding = generate_embeddings(content)
                        cursor.execute(
                            "INSERT INTO repo_files (file_name, content, embedding) VALUES (?, ?, ?)",
                            (file_info.filename, content, json.dumps(embedding)),
                        )

            conn.commit()
            conn.close()
            return "Repository saved to vector database successfully."
        except Exception as e:
            logger.error(f"Error saving repo to vector DB: {e}")
            return f"Error saving repo to vector DB: {e}"

    @mcp.tool()
    def extract_text_files(zip_file: zipfile.ZipFile):
        """Extract text/code files from the ZIP and return as {filename: content}"""
        file_contents = {}
        with tempfile.TemporaryDirectory() as tmpdirname:
            zip_file.extractall(tmpdirname)
            for root, _, files in os.walk(tmpdirname):
                for file in files:
                    ext = os.path.splitext(file)[1]
                    if ext in ALLOWED_EXTENSIONS:
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                                if content.strip():  # Skip empty files
                                    relative_path = os.path.relpath(
                                        file_path, tmpdirname
                                    )
                                    file_contents[relative_path] = content
                        except Exception:
                            pass  # Skip unreadable files
        return file_contents

    @mcp.resource("resource://agent_cards/list", mime_type="application/json")
    def get_agent_cards() -> dict:
        """Retrieves all loaded agent cards as a json / dictionary for the MCP resource endpoint.

        This function serves as the handler for the MCP resource identified by
        the URI 'resource://agent_cards/list'.

        Returns:
            A json / dictionary structured as {'agent_cards': [...]}, where the value is a
            list containing all the loaded agent card dictionaries. Returns
            {'agent_cards': []} if the data cannot be retrieved.
        """
        resources = {}
        logger.info("Starting read resources")
        resources["agent_cards"] = df["card_uri"].to_list()
        return resources

    @mcp.resource("resource://agent_cards/{card_name}", mime_type="application/json")
    def get_agent_card(card_name: str) -> dict:
        """Retrieves an agent card as a json / dictionary for the MCP resource endpoint.

        This function serves as the handler for the MCP resource identified by
        the URI 'resource://agent_cards/{card_name}'.

        Returns:
            A json / dictionary
        """
        resources = {}
        logger.info(f"Starting read resource resource://agent_cards/{card_name}")
        resources["agent_card"] = (
            df.loc[
                df["card_uri"] == f"resource://agent_cards/{card_name}",
                "agent_card",
            ]
        ).to_list()

        return resources

    logger.info(f"Agent cards MCP Server at {host}:{port} and transport {transport}")
    mcp.run(transport=transport)
