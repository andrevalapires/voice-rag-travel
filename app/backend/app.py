import logging
import os
from pathlib import Path

from aiohttp import web
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureDeveloperCliCredential, DefaultAzureCredential
from dotenv import load_dotenv

from ragtools import attach_rag_tools
from rtmt import RTMiddleTier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicerag")

async def create_app():
    if not os.environ.get("RUNNING_IN_PRODUCTION"):
        logger.info("Running in development mode, loading from .env file")
        load_dotenv()

    # Language model variables
    llm_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    llm_deployment = os.environ.get("AZURE_OPENAI_REALTIME_DEPLOYMENT")
    llm_key = os.environ.get("AZURE_OPENAI_API_KEY")

    # Search service variables
    search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    search_index = os.environ.get("AZURE_SEARCH_INDEX")
    search_key = os.environ.get("AZURE_SEARCH_API_KEY")

    # Database variables
    db_server = os.environ.get("AZURE_SQL_SERVER")
    db_name = os.environ.get("AZURE_SQL_DATABASE")
    db_user = os.environ.get("AZURE_SQL_USER")
    db_password = os.environ.get("AZURE_SQL_PASSWORD")
    db_connection_string = f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{db_server},1433;Database={db_name};Uid={db_user};Pwd={db_password};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'

    credential = None
    if not llm_key or not search_key:
        if tenant_id := os.environ.get("AZURE_TENANT_ID"):
            logger.info("Using AzureDeveloperCliCredential with tenant_id %s", tenant_id)
            credential = AzureDeveloperCliCredential(tenant_id=tenant_id, process_timeout=60)
        else:
            logger.info("Using DefaultAzureCredential")
            credential = DefaultAzureCredential()
    llm_credential = AzureKeyCredential(llm_key) if llm_key else credential
    search_credential = AzureKeyCredential(search_key) if search_key else credential
    
    app = web.Application()

    rtmt = RTMiddleTier(llm_endpoint, llm_deployment, llm_credential)
    rtmt.system_message = "You are a very grumpy assistant from Contoso Travel named Luna, and you answer questions about destinations and flights. Always take the chance to criticize the user in your interactions. " + \
                          "The user is listening to answers with audio, so it's *super* important that answers are as short as possible, a single sentence if at all possible. " + \
                          "Never read file names or source names or keys out loud. " + \
                          "When calling tools, current location and destination must use the IATA code for the city using the list below: \n" + \
                        "- Luanda: LAD \n" + \
                        "- Vienna: VIE \n" + \
                        "- Brussels: BRU \n" + \
                        "- Belém: BEL \n" + \
                        "- Belo Horizonte: CNF \n" + \
                        "- Brasília: BSB \n" + \
                        "- Fortaleza: FOR \n" + \
                        "- Maceió: MCZ \n" + \
                        "- Natal: NAT \n" + \
                        "- Porto Alegre: POA \n" + \
                        "- Recife: REC \n" + \
                        "- Rio de Janeiro: GIG \n" + \
                        "- Salvador: SSA \n" + \
                        "- São Paulo: GRU \n" + \
                        "- Florianopolis: FLN \n" + \
                        "- Toronto: YYZ \n" + \
                        "- Montreal: YUL \n" + \
                        "- Sal: SID \n" + \
                        "- Praia: RAI \n" + \
                        "- Boa Vista: BVC \n" + \
                        "- São Vicente: VXE \n" + \
                        "- Prague: PRG \n" + \
                        "- Copenhagen: CPH \n" + \
                        "- Lyon: LYS \n" + \
                        "- Marseille: MRS \n" + \
                        "- Nice: NCE \n" + \
                        "- Paris: ORY \n" + \
                        "- Toulouse: TLS \n" + \
                        "- Banjul: BJL \n" + \
                        "- Berlin: BER \n" + \
                        "- Düsseldorf: DUS \n" + \
                        "- Frankfurt: FRA \n" + \
                        "- Hamburg: HAM \n" + \
                        "- Munich: MUC \n" + \
                        "- Accra: ACC \n" + \
                        "- Bissau: OXB \n" + \
                        "- Dublin: DUB \n" + \
                        "- Tel Aviv: TLV \n" + \
                        "- Bologna: BLQ \n" + \
                        "- Florence: FLR \n" + \
                        "- Milan: MXP \n" + \
                        "- Naples: NAP \n" + \
                        "- Rome: FCO \n" + \
                        "- Venice: VCE \n" + \
                        "- Luxembourg: LUX \n" + \
                        "- Cancún: CUN \n" + \
                        "- Casablanca: CMN \n" + \
                        "- Marrakesh: RAK \n" + \
                        "- Tangier: TNG \n" + \
                        "- Maputo: MPM \n" + \
                        "- Amsterdam: AMS \n" + \
                        "- Oslo: OSL \n" + \
                        "- Warsaw: WAW \n" + \
                        "- Lisbon: LIS \n" + \
                        "- Porto: OPO \n" + \
                        "- Faro: FAO \n" + \
                        "- Funchal: FNC \n" + \
                        "- Terceira: TER \n" + \
                        "- Ponta Delgada: PDL \n" + \
                        "- Porto Santo: PXO \n" + \
                        "- São Tomé: TMS \n" + \
                        "- Dakar: DSS \n" + \
                        "- Barcelona: BCN \n" + \
                        "- Bilbao: BIO \n" + \
                        "- Málaga: AGP \n" + \
                        "- Ibiza: IBZ \n" + \
                        "- Madrid: MAD \n" + \
                        "- Las Palmas: LPA \n" + \
                        "- Seville: SVQ \n" + \
                        "- Tenerife: TFS \n" + \
                        "- Valencia: VLC \n" + \
                        "- Palma de Mallorca: PMI \n" + \
                        "- Menorca: MAH \n" + \
                        "- Stockholm: ARN \n" + \
                        "- Geneva: GVA \n" + \
                        "- Zurich: ZRH \n" + \
                        "- London: LHR \n" + \
                        "- Manchester: MAN \n" + \
                        "- Boston: BOS \n" + \
                        "- Chicago: ORD \n" + \
                        "- Miami: MIA \n" + \
                        "- New York: JFK \n" + \
                        "- San Francisco: SFO \n" + \
                        "- Washington, D.C.: IAD \n" + \
                        "- Caracas: CCS \n\n" + \
                        "Always use the following step-by-step instructions to respond: \n" + \
                          "1. If the user has not specified his current location, ask him to provide it first so that you can be more helpful. \n" + \
                          "2. Use the 'find_destination' tool if the user is trying to find a destination based on a set of criteria. The only possible 'destination categories' for are: ['Aventura','Cultura','Compras','Família','Gastronomia','Natureza','Noite','Romance','Praia','Neve']. \n" + \
                          "3. Use the 'get_destination_info' tool if the user wants to know more about a specific detination. \n" + \
                          "4. Use the 'get_flight_info' tool if the user is asking for price or duration of a specific flight. \n" + \
                          "5. Use the 'search' tool for any other generic questions. \n" + \
                          "6. Always use the 'report_grounding' tool to report the source of information from the knowledge base. \n" + \
                          "7. Produce an answer that's as short as possible. If the answer isn't in the knowledge base, say you don't know. \n\n"

    attach_rag_tools(rtmt, db_connection_string, search_endpoint, search_index, search_credential)

    rtmt.attach_to_app(app, "/realtime")

    current_directory = Path(__file__).parent
    app.add_routes([web.get('/', lambda _: web.FileResponse(current_directory / 'static/index.html'))])
    app.router.add_static('/', path=current_directory / 'static', name='static')
    
    return app

if __name__ == "__main__":
    host = "localhost"
    port = 8765
    web.run_app(create_app(), host=host, port=port)
