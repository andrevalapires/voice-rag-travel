import re
import pyodbc
import json
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import (
    VectorizableTextQuery,
    VectorizedQuery,
    QueryType,
    QueryCaptionType,
    QueryAnswerType,
)
from rtmt import RTMiddleTier, Tool, ToolResult, ToolResultDirection

_find_destination_tool_schema = {
    "type": "function",
    "name": "find_destination",
    "description": "Find a destination using a set of criteria. Possible criteria is " + \
                   "the user's current location, the maximum flight duration, the maximum flight price, " + \
                   "the categories of the destination, and generic content to search for about the destination. " + \
                   "The knowledge base is in Portuguese, translate to and from Portuguese if needed. " + \
                   "Results are formatted as a source name first in square brackets, followed by the text content, and a line with '-----' at the end of each result.",
    "parameters": {
        "type": "object",
        "properties": {
            "current_location": {
                "type": "string",
                "description": "The user's current location using the IATA code for the city"
            },
            "max_flight_duration": {
                "type": "integer",
                "description": "The maximum flight duration in hours"
            },
            "max_price": {
                "type": "number",
                "description": "The maximum price in EUR"
            },
            "categories": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "The categories of the destination"
            },
            "content": {
                "type": "string",
                "description": "Generic content to search for about the destination"
            }
        },
        "required": ["current_location"],
        "additionalProperties": False
    }
}

_get_destination_info_tool_schema = {
    "type": "function",
    "name": "get_destination_info",
    "description": "Get information about a specific destination using the knowledge base. The knowledge base is in Portuguese, " + \
                   "translate to and from Portuguese if needed. Results are formatted as a source name first in square brackets, " + \
                   "followed by the text content, and a line with '-----' at the end of each result.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question about the destination"
            }
        },
        "required": ["query"],
        "additionalProperties": False
    }
}

_get_flight_info_tool_schema = {
    "type": "function",
    "name": "get_flight_info",
    "description": "Get the price and duration of a specific flight between two cities at a specific date. " + \
                    "The flight information is returned as a JSON object with 5 properties: 'source', 'destination', " + \
                    "'price', 'duration', and 'trip_date'.",
    "parameters": {
        "type": "object",
        "properties": {
            "current_location": {
                "type": "string",
                "description": "The user's current location using the IATA code for the city"
            },
            "destination": {
                "type": "string",
                "description": "The destination using the IATA code for the city"
            },
            "trip_date": {
                "type": "string",
                "description": "The date of the trip in the format 'YYYY-MM-DD'"
            }
        },
        "required": ["current_location", "destination", "trip_date"],
        "additionalProperties": False
    }
}

_search_tool_schema = {
    "type": "function",
    "name": "search",
    "description": "Search the knowledge base for a generic query. The knowledge base is in Portuguese, translate to and from Portuguese if " + \
                   "needed. Results are formatted as a source name first in square brackets, followed by the text " + \
                   "content, and a line with '-----' at the end of each result.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            }
        },
        "required": ["query"],
        "additionalProperties": False
    }
}

_grounding_tool_schema = {
    "type": "function",
    "name": "report_grounding",
    "description": "Report use of a source from the knowledge base as part of an answer (effectively, cite the source). Sources " + \
                   "appear in square brackets before each knowledge base passage. Always use this tool to cite sources when responding " + \
                   "with information from the knowledge base.",
    "parameters": {
        "type": "object",
        "properties": {
            "sources": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "List of source names from last statement actually used, do not include the ones not used to formulate a response"
            }
        },
        "required": ["sources"],
        "additionalProperties": False
    }
}

# Retrieves the destinations with a flight duration less than or equal to the specified duration
def get_destinations_by_duration(source: str, duration: float, conn) -> str:
    # SQL query to select the destinations with a flight duration less than or equal to the specified duration
    query = """
    SELECT Destination
    FROM dbo.FlightDuration
    WHERE Source = ? AND Duration <= ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, duration))

    # Fetch the results
    rows = cursor.fetchall()

    # Check if we got any results
    if rows:
        # Extract the destinations from the result
        destinations = [row.Destination for row in rows]
        return json.dumps(destinations)  # Return the destinations as a JSON string
    else:
        return json.dumps([])  # Return an empty list if no data is found

# Retrieves the destinations with a flight price less than or equal to the specified price
def get_destinations_by_price(source: str, price: float, conn) -> str:
    # SQL query to select the destinations with a flight price less than or equal to the specified price
    query = """
    SELECT Destination
    FROM dbo.FlightPrice
    WHERE Source = ? AND Price <= ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, price))

    # Fetch the results
    rows = cursor.fetchall()

    # Check if we got any results
    if rows:
        # Extract the destinations from the result
        destinations = [row.Destination for row in rows]
        return json.dumps(destinations)  # Return the destinations as a JSON string
    else:
        return json.dumps([])  # Return an empty list if no data is found

# Tool to find a destination using a set of criteria
async def _find_destination_tool(db_conn_string: str, search_client: SearchClient, args: Any) -> ToolResult:
    print("Finding destination with the following criteria:")
    print(f"- Current location '{args['current_location']}'")
    source = args["current_location"]

    if "max_flight_duration" in args:
        print(f"- Max flight duration {args['max_flight_duration']} hours")
        duration = args["max_flight_duration"]
    else:
        duration = None

    if "max_price" in args:
        print(f"- Max price {args['max_price']} EUR")
        price = args["max_price"]
    else:
        price = None

    if "categories" in args:
        print(f"- Categories {args['categories']}")
        categories = args["categories"]
    else:
        categories
    
    if "content" in args:
        print(f"- Content '{args['content']}'")
        content = args["content"]
    else:
        content = None

    # open a connection to the database
    conn = pyodbc.connect(db_conn_string)

    # Get the destinations by duration
    destinations_by_duration = []
    if duration:
        destinations_by_duration = json.loads(get_destinations_by_duration(source, duration, conn))
        print(f"Destinations by duration: {destinations_by_duration}")

    # Get the destinations by price
    destinations_by_price = []
    if price:
        destinations_by_price = json.loads(get_destinations_by_price(source, price, conn))
        print(f"Destinations by price: {destinations_by_price}")

    # Close the database connection
    conn.close()

    # Generate filter string based on destinations that satisfy both duration and price constraints
    filter_string = ""

    if destinations_by_duration and destinations_by_price:
        intersection_of_destinations = list(set(destinations_by_duration) & set(destinations_by_price))
    elif destinations_by_duration:
        intersection_of_destinations = destinations_by_duration
    else:
        intersection_of_destinations = destinations_by_price

    if intersection_of_destinations:
        # Generate the filter string based on iata_code values in intersection_of_destinations
        destination_filter_parts = [f"iata_code eq '{destination}'" for destination in intersection_of_destinations]
        filter_string = " or ".join(destination_filter_parts)

    # Generate filter string based on categories
    if categories:
        category_filter_parts = [f"categories/any(c: c eq '{category}')" for category in categories]
        category_filter_string = " and ".join(category_filter_parts)
        if filter_string:
            filter_string = f"({filter_string}) and ({category_filter_string})"
        else:
            filter_string = category_filter_string

    print(f"Filter String: {filter_string}")

    # Search for the destinations based on the user's question
    if content is None:
        content = "travel"

    search_results = await search_client.search(
        search_text=content,
        vector_queries=[VectorizableTextQuery(text=content, k_nearest_neighbors=50, fields="destination_vector, country_vector")],
        query_type=QueryType.SEMANTIC,
        semantic_configuration_name="semantic-tap",
        query_caption=QueryCaptionType.EXTRACTIVE,
        query_answer=QueryAnswerType.EXTRACTIVE,
        top=5,
        filter=filter_string
    )

    result = ""
    async for item in search_results:
        item_string = f"[{item['destination']} @KB]: Destination: {item['destination']}\n{item['destination_pt']}\nCountry: {item['country']}\n{item['country_pt']}\nCategories: {item['categories']}\n-----\n"
        print(f"Found destination: {item_string}")
        result += item_string

    #result = "[Paris@KB]: Destination: Paris\nPrice: 200 EUR\nDuration: 2.5 hours\n-----\n"
    #result += "[Madrid@KB]: Destination: Madrid\nPrice: 147 EUR\nDuration: 1.5 hours\n-----\n"
    #result += "[Barcelona@KB]: Destination: Barcelona\nPrice: 178 EUR\nDuration: 2 hours\n-----\n"

    return ToolResult(result, ToolResultDirection.TO_SERVER)

# Tool to get information about a specific destination
async def _get_destination_info_tool(search_client: SearchClient, args: Any) -> ToolResult:
    print(f"Getting information about destination for query '{args['query']}'")

    search_results = await search_client.search(
        search_text=args['query'], 
        vector_queries=[VectorizableTextQuery(text=args['query'], k_nearest_neighbors=3, fields="destination_vector, country_vector")],
        query_type=QueryType.SEMANTIC,
        top=3,
        semantic_configuration_name="semantic-tap",
        query_caption=QueryCaptionType.EXTRACTIVE,
        query_answer=QueryAnswerType.EXTRACTIVE
    )

    result = ""
    async for item in search_results:
        item_string = f"[{item['destination']} @KB]: Destination: {item['destination']}\n{item['destination_pt']}\nCountry: {item['country']}\n{item['country_pt']}\nCategories: {item['categories']}\n-----\n"
        print(f"Found destination: {item_string}")
        result += item_string

    print(f"Search results: {result}")

    #result = "[Paris@KB]: Paris is the capital of France and is known for its art, fashion, gastronomy, and culture.\n-----\n"
    #result += "[Madrid@KB]: Madrid is the capital of Spain and is known for its elegant boulevards and expansive parks.\n-----\n"
    #result += "[Barcelona@KB]: Barcelona is the capital of Catalonia and is known for its art and architecture.\n-----\n"

    return ToolResult(result, ToolResultDirection.TO_SERVER)

# Retrieves the duration of a flight between two locations
def get_flight_duration(source: str, destination: str, conn) -> float:
    # SQL query to select the flight duration
    query = """
    SELECT Duration
    FROM dbo.FlightDuration
    WHERE Source = ? AND Destination = ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, destination))

    # Fetch the result
    row = cursor.fetchone()

    # Check if we got a result
    if row:
        return row.Duration # Return the duration value from the result
    else:
        return 0.0  # Return 0.0 or an appropriate value if no data is found

# Retrieves the price of a flight between two locations
def get_flight_price(source: str, destination: str, trip_date: str, conn) -> float:
    # SQL query to select the flight price
    query = """
    SELECT Price
    FROM dbo.FlightPrice
    WHERE Source = ? AND Destination = ? AND StartDate <= ? AND EndDate >= ?
    """
    # Execute the query
    cursor = conn.cursor()
    cursor.execute(query, (source, destination, trip_date, trip_date))
    
    # Fetch the result
    row = cursor.fetchone()
    
    # Check if we got a result
    if row:
        return float(row.Price)  # Return the price value from the result
    else:
        return 0.0  # Return 0.0 or an appropriate value if no data is found

# Tool to get the price and duration of a specific flight
async def _get_flight_info_tool(db_conn_string: str, args: Any) -> ToolResult:
    print(f"Getting flight information for current location '{args['current_location']}' to destination '{args['destination']}' at trip date '{args['trip_date']}'")

    # open a connection to the database
    conn = pyodbc.connect(db_conn_string)

    duration = get_flight_duration(args["current_location"], args["destination"], conn)
    price = get_flight_price(args["current_location"], args["destination"], args["trip_date"], conn)

    result = {
        "source": args["current_location"],
        "destination": args["destination"],
        "price": price,
        "duration": duration,
        "trip_date": args["trip_date"]
    }

    # close the database connection
    conn.close()

    print(f"Flight information: {result}")

    return ToolResult(result, ToolResultDirection.TO_SERVER)

# Tool to search the knowledge base for a generic query
async def _search_tool(search_client: SearchClient, args: Any) -> ToolResult:
    print(f"Searching for '{args['query']}' in the knowledge base.")
    
    # Hybrid + Reranking query using Azure AI Search
    search_results = await search_client.search(
        search_text=args['query'], 
        query_type="semantic",
        top=5,
        vector_queries=[VectorizableTextQuery(text=args['query'], k_nearest_neighbors=50, fields="text_vector")],
        select="chunk_id,title,chunk")
    
    result = ""
    async for r in search_results:
        result += f"[{r['chunk_id']}]: {r['chunk']}\n-----\n"
    
    print(f"Search results: {result}")
    
    return ToolResult(result, ToolResultDirection.TO_SERVER)

KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_=\-]+$')

# TODO: move from sending all chunks used for grounding eagerly to only sending links to 
# the original content in storage, it'll be more efficient overall
async def _report_grounding_tool(search_client: SearchClient, args: Any) -> None:
    if "sources" in args:
        print(f"Reporting grounding for sources: {args['sources']}")
    else:
        print("Reporting grounding for no sources")
    
    sources = [s for s in args["sources"] if KEY_PATTERN.match(s)]
    list = " OR ".join(sources)
    print(f"Grounding source: {list}")

    # Use search instead of filter to align with how detailt integrated vectorization indexes
    # are generated, where chunk_id is searchable with a keyword tokenizer, not filterable 
    '''
    search_results = await search_client.search(
        search_text=list, 
        search_fields=["chunk_id"], 
        select=["chunk_id", "title", "chunk"], 
        top=len(sources), 
        query_type="full"
    )
    '''

    # If your index has a key field that's filterable but not searchable and with the keyword analyzer, you can 
    # use a filter instead (and you can remove the regex check above, just ensure you escape single quotes)
    # search_results = await search_client.search(filter=f"search.in(chunk_id, '{list}')", select=["chunk_id", "title", "chunk"])
    '''
    docs = []
    async for r in search_results:
        docs.append({"chunk_id": r['chunk_id'], "title": r["title"], "chunk": r['chunk']})
    '''
    
    return ToolResult({"sources": sources}, ToolResultDirection.TO_CLIENT)

# Attaches the RAG tools to the RTMiddleTier
def attach_rag_tools(rtmt: RTMiddleTier, db_conn_string: str, search_endpoint: str, search_index: str, credentials: AzureKeyCredential | DefaultAzureCredential) -> None:
    if not isinstance(credentials, AzureKeyCredential):
        credentials.get_token("https://search.azure.com/.default") # warm this up before we start getting requests
    search_client = SearchClient(search_endpoint, search_index, credentials, user_agent="RTMiddleTier")

    rtmt.tools["find_destination"] = Tool(schema=_find_destination_tool_schema, target=lambda args: _find_destination_tool(db_conn_string, search_client, args))
    rtmt.tools["get_destination_info"] = Tool(schema=_get_destination_info_tool_schema, target=lambda args: _get_destination_info_tool(search_client, args))
    rtmt.tools["get_flight_info"] = Tool(schema=_get_flight_info_tool_schema, target=lambda args: _get_flight_info_tool(db_conn_string, args))
    rtmt.tools["search"] = Tool(schema=_search_tool_schema, target=lambda args: _search_tool(search_client, args))
    rtmt.tools["report_grounding"] = Tool(schema=_grounding_tool_schema, target=lambda args: _report_grounding_tool(search_client, args))
