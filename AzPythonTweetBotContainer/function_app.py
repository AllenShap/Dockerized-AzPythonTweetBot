import requests
import xml.etree.ElementTree as ET 
import datetime
import json
import os
import time
import tweepy
import logging
import azure.functions as func
from os import listdir
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential
from PIL import Image, ImageDraw, ImageFont
import textwrap
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.print_page_options import PrintOptions
from webdriver_manager.firefox import GeckoDriverManager
from datetime import timedelta
from datetime import timezone
import base64
import uuid
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, generate_blob_sas, BlobSasPermissions
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
from azure.ai.textanalytics import ExtractiveSummaryAction
from azure.ai.textanalytics import AbstractiveSummaryAction
from azure.ai.language.questionanswering import QuestionAnsweringClient
from azure.ai.language.questionanswering import models as qna
from pdfminer.high_level import extract_text
from unidecode import unidecode
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.sdk.trace import SpanProcessor

CONTAINERNAME = os.environ['COSMOS_DB_CONTAINER_NAME'] 
ENDPOINT = os.environ['COSMOS_DB_ENDPOINT']                                                         
DATABASENAME = os.environ['COSMOS_DB_NAME']                                                                  
CREDENTIAL = os.environ['COSMOS_DB_CREDENTIAL']
CONSUMER_KEY = os.environ['TWITTER_CONSUMER_KEY']                                                      #You need a Twitter dev account to get these credentials and make a tweet.
CONSUMER_SECRET = os.environ['TWITTER_CONSUMER_SECRET']                                                 #These variables are for Twitter API credentials
ACCESS_TOKEN = os.environ['TWITTER_ACCESS_TOKEN']
ACCESS_TOKEN_SECRET = os.environ['TWITTER_ACCESS_TOKEN_SECRET']

AZURE_COGNITIVE_ENDPOINT = os.environ['COGNITIVE_ENDPOINT']
AZURE_COGNITIVE_KEY = os.environ['COGNITIVE_KEY']
AZURE_COGNITIVE_SEARCH_ENDPOINT = os.environ['COGNITIVE_SEARCH_ENDPOINT']
AZURE_COGNITIVE_SEARCH_KEY = os.environ['COGNITIVE_SEARCH_KEY']
AZURE_APPLICATION_INSIGHTS_CONNECTION_STRING = os.environ['APPLICATIONINSIGHTS_CONNECTION_STRING']


class SpanEnrichingProcessor(SpanProcessor):
    def on_end(self, span):
        if not span.name.startswith("OfficialDevelopment-"):
            span._name = "OfficialDevelopment-" + span.name
            span._attributes["enduser.id"] = "DEVELOPMENT"

span_enrich_processor = SpanEnrichingProcessor()
configure_azure_monitor(connection_string=AZURE_APPLICATION_INSIGHTS_CONNECTION_STRING, span_processors=[span_enrich_processor])



app = func.FunctionApp()
@app.function_name(name="mytimer")
@app.schedule(schedule="0 */5 * * * 0-6", arg_name="myTimer", run_on_startup=True,
              use_monitor=False) 
def timer_trigger_tweeter(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc).isoformat()
    global tracer
    tracer = trace.get_tracer(__name__,tracer_provider=trace.get_tracer_provider())

    global DBENTRYNEWSTIMESTAMPQUERYVALUE
    global DBENTRYNEWSTIMESTAMP
    global DBID
    global XMLQUERYCURRENTDATE
    global client
    global database
    global partitionKeyPath
    global container
    global datesList
    global linksList
    global titleList
    global allPubDates
    global r
    DBENTRYNEWSTIMESTAMPQUERYVALUE = '{:%a, %d %b %Y}'.format(datetime.datetime.utcnow())
    XMLQUERYCURRENTDATE = [f'{DBENTRYNEWSTIMESTAMPQUERYVALUE}']
    DBENTRYNEWSTIMESTAMP = '{:%Y-%m-%d %H:%M:%S.%f}'.format(datetime.datetime.utcnow())
    DBID = '{:%a, %d %b %Y}'.format(datetime.datetime.utcnow())
    DBQUERYID = '{:%Y-%m-%d}'.format(datetime.datetime.utcnow())
    client = CosmosClient(url=ENDPOINT, credential=CREDENTIAL)
    database = client.create_database_if_not_exists(id=DATABASENAME)
    partitionKeyPath = PartitionKey(path="/categoryId")
    container = database.create_container_if_not_exists(id=CONTAINERNAME, partition_key=partitionKeyPath)
    datesList = []
    linksList = []
    titleList = []
    allPubDates = []
    r = None
    r = requests.get("https://www.nytimes.com/svc/collections/v1/publish/https://www.nytimes.com/section/us/rss.xml")




    deleteAllTxtFiles()             #if the previous run of this program ends up calling exit(), it will delete all .txt files from the previous session since exit()-ing an azure function doesn't actually reset the worker and clear C:/Users/ostrich/Desktop/AzureDeploymentTweeterLinux/.
    summarizationFileDeletion()

    countEntriesInCosmosDB()
    countEntriesInXML()
    getXMLEntriesMissingFromDB()
    searchForMissingXMLDatesInTheDB()


    global finalTitlesToBeInserted
    global finalLinksToBeInserted
    global finalDatesToBeInserted
    finalTitlesToBeInserted = []
    finalDatesToBeInserted = []
    finalLinksToBeInserted = []
 

    list(map(compareTitlesInDBWithXMLEntriesToPreventDuplicateEntries, linelist))

    PushEntriesToAddToAPI(finalTitlesToBeInserted, finalLinksToBeInserted, finalDatesToBeInserted)


    with tracer.start_as_current_span("STEP_ONE") as span:
        removeDuplicateXMLEntries()
        span.set_attribute("STEP_ONE_RESULTS_OUTPUT",f"{uniqueDates},{uniqueTitles},{uniqueLinks}")


    with tracer.start_as_current_span("STEP_TWO_FOR_UPDATED_TWEET_DATA") as span:
        checkForDuplicateArticleLinksInDB(uniqueLinks)
        span.set_attribute("STEP_TWO_FOR_UPDATED_TWEET_DATA",f"OLD:{matchedLinks},{matchedTitles},{matchedDates},{updatedLinks},UPDATED:{updatedTitles},{updatedDates},{updatedLinks}")

    with tracer.start_as_current_span("STEP_THREE_MAKING_TWEET") as span:
        span.set_attribute("STEP_THREE_MAKING_TWEET",f"{uniqueDates},{uniqueTitles},{uniqueLinks}")
        list(map(makeTweetWithInsertedEntryInCosmosDB,uniqueDates,uniqueTitles,uniqueLinks))

    
    deleteAllTxtFiles()
    titleList = None
    datesList = None
    linksList = None
    allPubDates = None

    
def countEntriesInCosmosDB():
    cosmosDBQuery = None
    EntryNewsTimestamp = None
    params = None
    results = None
    items = None
    listOfItemsInDB = None

    cosmosDBQuery = "SELECT * FROM " +CONTAINERNAME+ " p WHERE p.EntryNewsTimestamp LIKE @EntryNewsTimestamp"                                                                                         
    EntryNewsTimestamp = f"{DBENTRYNEWSTIMESTAMPQUERYVALUE}%"                                               
    params = [dict(name="@EntryNewsTimestamp", value=EntryNewsTimestamp)]                                   
    results = container.query_items(
        query=cosmosDBQuery, parameters=params, enable_cross_partition_query=True
    )

    items = [item for item in results]

    if items == []:
        listOfItemsInDB = []
    if (len(items)) == 0:
        print("No items are found in the DB that are today's date.")
    else:
        listOfItemsInDB = []
        x = range(len(items))
        for i in x:
            listOfItemsInDB.append(items[i]["EntryNewsTimestamp"])

    if listOfItemsInDB == []:
        url = f"http://0.0.0.0:8001/items/Function1Output"
        txt = f"There are no items in the Cosmos DB. Getting the latest entry in the nytimes rss xml."
        putPayload = {"name" : txt}
        requests.put(url, json=putPayload)

    else:
        print("Found items in the DB that are today's date.")
        url = f"http://0.0.0.0:8001/items/Function1Output"
        txt = f"{listOfItemsInDB}"
        putPayload = {"name" : txt}
        requests.put(url, json=putPayload)


def countEntriesInXML(): 
    f = None
    lines = None
    linelist = None
    root = None
    pubDatez = None
    y = None
    filtered_dates = None
    notInDB = None

    url = f"http://0.0.0.0:8001/items/Function1Output"
    ar = requests.get(url)
    linelist = ar.json()

    root = ET.fromstring(r.text)

    pubDatez = [pubDate.text for pubDate in root[0].iter('pubDate')]                               
    pubDatez.pop(0)                                                                                
    y = XMLQUERYCURRENTDATE       #Tue, 16 Jan 2024 - is the timestamp format being followed
    filtered_dates = [date for date in pubDatez if y[0] in date]
    notInDB = []

    if filtered_dates == linelist[0]:                                                                                                           
        print("There are no items that need to be added to the db")
        quit
    else:
        for i in filtered_dates:
            if i not in linelist:
                notInDB.append(i)
        else:
            print("THESE ARE THE ITEMS THAT I NEED TO FIND THE DETAILS OF BELOW(ITEMS NOT IN THE DATABASE):")
            print(notInDB)
            
            url = f"http://0.0.0.0:8001/items/CountEntriesInXML"
            txt = f"{notInDB}"
            putPayload = {"name" : txt}
            requests.put(url, json=putPayload)


def getXMLEntriesMissingFromDB():
    f = None
    lines = None
    linelist = None
    root = None
    var = None
    loopedPubDates = None
    loopedPubDates = []
    url = f"http://0.0.0.0:8001/items/CountEntriesInXML"
    ar = requests.get(url)
    linelist = []
    linelist = ar.json()

    
    root = ET.fromstring(r.text)
    for pubdate in root.iter('channel'):                   
        print("Placeholder text")                                   #Just need this to complete for statement
        for pubdate2 in pubdate.iter('pubDate'):                    
            allPubDates.append(pubdate2.text)
 
    var = [(i) for i in allPubDates]
    for i in range(len(var)):
        if var[i] in linelist:
            print("THE FOLLOWING VALUES ARE THE VALUES MISSING FROM THE DATABASE")
            print(var[(i)])
            loopedPubDates.append(var[(i)])


    url = f"http://0.0.0.0:8001/items/ItemsToFindFromFunc3"
    txt = f"{loopedPubDates}"
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)


    url = f"http://0.0.0.0:8001/items/ItemsToFindFromFunc3"
    ar = requests.get(url)
    linelist = ar.json()


def searchForMissingXMLDatesInTheDB():
    f = None
    lines = None
    root = None
    pubtitle = None
    pubDatez = None
    pubtitle = None
    publink = None
    pubDatezList = None
    x = None
    pubDatezMatching = None
    indexOfItemsINeedToGet = None

    url = f"http://0.0.0.0:8001/items/ItemsToFindFromFunc3"
    ar = requests.get(url)
    
    global linelist
    linelist = ar.json()




    root = ET.fromstring(r.text)
    pubtitle = [title.text for title in root[0].iter('title')]
    todaytitle = pubtitle[2]
    pubDatez = [pubDate.text for pubDate in root[0].iter('pubDate')]
    pubtitle = [title.text for title in root[0].iter('title')]
    publink = [link.text for link in root[0].iter('link')]
    publink.pop(0)
    publink.pop(0)
    pubtitle.pop(0)
    pubtitle.pop(0)
    pubDatez.pop(0)
    pubTitleList = []
    pubLinkList = []
    pubDatezList = pubDatez

    x = range(len(pubDatez))
    for n in x:
        pubTitleList.append(pubtitle[n])
        pubLinkList.append(publink[n])

    pubDatezMatching = ([item for item in pubDatezList if item in linelist])

    print(pubDatezMatching)
    indexOfItemsINeedToGet = [pubDatezList.index(i) for i in pubDatezMatching]

    datesToBeInsertedIntoDB = []
    titlesToBeInsertedIntoDB = []
    linksToBeInsertedIntoDB = []
    test = []

    for i in indexOfItemsINeedToGet:
        print(i, pubDatez[i])
        print(i, pubTitleList[i])
        print(i, pubLinkList[i])
        datesToBeInsertedIntoDB.append(pubDatez[i])
        linksToBeInsertedIntoDB.append(pubLinkList[i])
        titlesToBeInsertedIntoDB.append(pubTitleList[i])
    for i in titlesToBeInsertedIntoDB:
        test.append(i)


        
    url = f"http://0.0.0.0:8001/items/LinksToFindFromFunc4"
    txt = linksToBeInsertedIntoDB
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)


    url = f"http://0.0.0.0:8001/items/DatesToFindFromFunc4"
    txt = datesToBeInsertedIntoDB
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)


    url = f"http://0.0.0.0:8001/items/TitlesToFindFromFunc4"
    txt = titlesToBeInsertedIntoDB
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)


    global titles
    url = f"http://0.0.0.0:8001/items/TitlesToFindFromFunc4"
    ar = requests.get(url)
    titles = ar.json()
    linelist = titles


    global links
    url = f"http://0.0.0.0:8001/items/LinksToFindFromFunc4"
    ar = requests.get(url)
    links = ar.json()

    global dates
    url = f"http://0.0.0.0:8001/items/DatesToFindFromFunc4"
    ar = requests.get(url)
    dates = ar.json()


def compareTitlesInDBWithXMLEntriesToPreventDuplicateEntries(XMLtitlesToCompareWith):
    EntryNewsTitle = None
    cosmosDBQuery= None
    params = None
    results = None
    items = None
    output = None
    itemsdict = None
    EntryInDB = None
    f = None
    lines = None
    
    print("compareTitlesInDBWithXMLEntriesToPreventDuplicateEntries")
    cosmosDBQuery = "SELECT * FROM " +CONTAINERNAME+ " p WHERE p.EntryNewsTitle LIKE @EntryNewsTitle"                                                                                        
    EntryNewsTitle = XMLtitlesToCompareWith                                                         
    params = [dict(name="@EntryNewsTitle", value=EntryNewsTitle)]                                           
    results = container.query_items(                                                               
        query=cosmosDBQuery, parameters=params, enable_cross_partition_query=True               
    )
    items = [item for item in results]
    output = json.dumps(items, indent=True)
    if not items:
        print("The item to be inserted is not a duplicate")             #Crude explanation: When you get the latest entry in DB, match it with last entry made to make sure it's not a duplicate entry to be made, if it's duplicate; exclaim its a duplicate and won't be Tweeted/Inserted.
    else:
        itemsdict = items[0]                                                                  
        EntryInDB = itemsdict["EntryNewsTitle"]
    if (len(items)) == 0:
        finalTitlesToBeInserted.append(titles[linelist.index(EntryNewsTitle)])
        finalLinksToBeInserted.append(links[linelist.index(EntryNewsTitle)])
        finalDatesToBeInserted.append(dates[linelist.index(EntryNewsTitle)])
    else:
        listOfTitlesInDB = []
        x = range(len(items))
        for i in x:
            print(items[i]["EntryNewsTitle"] , "is a duplicate. It will not be inserted into the DB or Tweeted.")
            listOfTitlesInDB.append(items[i]["EntryNewsTitle"])


def PushEntriesToAddToAPI(titles, links, dates):
    url = f"http://0.0.0.0:8001/items/DatesToInsert"
    txt = dates
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)

    url = f"http://0.0.0.0:8001/items/LinksToInsert"
    txt = links
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)

    url = f"http://0.0.0.0:8001/items/TitlesToInsert"
    txt = titles
    putPayload = {"name" : txt}
    requests.put(url, json=putPayload)


def removeDuplicateXMLEntries():
    url = f"http://0.0.0.0:8001/items/TitlesToInsert"
    ar = requests.get(url)
    titleList = ar.json()

    url = f"http://0.0.0.0:8001/items/LinksToInsert"
    ar = requests.get(url)
    linksList = ar.json()

    url = f"http://0.0.0.0:8001/items/DatesToInsert"
    ar = requests.get(url)
    datesList = ar.json()


    global uniqueTitles
    global uniqueDates
    global uniqueLinks
    seenTitles = set()
    seenDates = set()
    seenLinks = set()
    uniqueTitles = []
    uniqueDates = []
    uniqueLinks = []
    print("\n Initiating duplicate check number 2 \n")

    for date in datesList:
        if date not in seenDates:
            seenDates.add(date)
            uniqueDates.append(date)
            print(date , "is OK to be inserted into the db. confirmed non-duplicate")
    for title in titleList:
        if title not in seenTitles:
            seenTitles.add(title)
            uniqueTitles.append(title)
            print(title , "is OK to be inserted into the db. confirmed non-duplicate")
    for links in linksList:
        if links not in seenLinks:
            seenLinks.add(links)
            uniqueLinks.append(links)
            print(links , "is OK to be inserted into the db. confirmed non-duplicate")
    

def checkForDuplicateArticleLinksInDB(linkToCheck):
    global items
    cosmosDBQuery = None
    EntryNewsLink = None
    params = None
    results = None
    items = None

    global matchedLinks
    global matchedTitles
    global matchedDates
    global updatedTitles
    global updatedLinks
    global updatedDates

    matchedLinks = []                               #List that will hold old article entries
    matchedTitles = []
    matchedDates = []

    updatedTitles = []                                      #List that will hold updated article entries
    updatedLinks = []
    updatedDates = []

    for i in linkToCheck:
        cosmosDBQuery = "SELECT * FROM " +CONTAINERNAME+ " p WHERE p.EntryNewsLink LIKE @EntryNewsLink"                                                                                       
        EntryNewsLink = i
        params = [dict(name="@EntryNewsLink", value=EntryNewsLink)]
        results = container.query_items(
        query=cosmosDBQuery, parameters=params, enable_cross_partition_query=True
        )
        items = [item for item in results]                                                      #This items variable is actually sort of a list of dictionary values which explains the index navigation below

        if items != []:
            matchedLinks.append(items[0]["EntryNewsLink"])                                      #Gets old article entries
            matchedTitles.append(items[0]["EntryNewsTitle"])
            matchedDates.append(items[0]["EntryNewsTimestamp"])

            updatedLinks.append(i)                                                          #Gets updated article entries to Tweet
            updatedTitles.append(uniqueTitles[uniqueLinks.index(i)])
            updatedDates.append(uniqueDates[uniqueLinks.index(i)])

    print("Old article entry values:")
    print(matchedLinks)
    print(matchedTitles)
    print(matchedDates)
    print("New updated article entry values:")
    print(updatedLinks)
    print(updatedTitles)
    print(updatedDates)


def insertIntoCosmosDB(uniqueDates,uniqueTitles,uniqueLinks):                            
    print("insertIntoCosmosDB")
    DBENTRYNEWSTIMESTAMP = '{:%Y-%m-%d %H:%M:%S.%f}'.format(datetime.datetime.utcnow())

    new_item = {
        "id": DBENTRYNEWSTIMESTAMP,
        "EntryNewsTimestamp": uniqueDates,
        "categoryId": "61dba35b-4f02-45c5-b648-c6badc0cbd79",
        "EntryNewsTitle": uniqueTitles,
        "EntryNewsLink": uniqueLinks
    }
    container.create_item(new_item)
    print("Inserted new item into CosmosDB")


def seleniumfunction(LinkToGet):
    extension_path = "/home/site/wwwroot/remove_javascript.xpi"
    extension_path2 = "/home/site/wwwroot/image_block-5.0.xpi"
    extension_path3 = "/home/site/wwwroot/ublock_origin-1.56.0.xpi"
    download_dir = "/home/site/wwwroot/"
    options = webdriver.FirefoxOptions()
    options.set_preference("browser.download.manager.showWhenStarting",False)
    options.set_preference("browser.download.downloadDir", download_dir)
    options.set_preference("browser.helperApps.alwaysAsk.force", False)
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.manager.useWindow", False)
    options.set_preference("browser.download.dir", download_dir)
    options.set_preference("permissions.default.image", 2)
    options.set_preference("permissions.default.stylesheet", 2)
    options.set_preference("media.autoplay.default", 1) 
    options.set_preference("media.autoplay.enabled.user-gestures-needed", False)
    options.set_preference("media.autoplay.blocking_policy", 2)
    options.set_preference("browser.display.use_document_fonts", 0)
    options.set_preference("extensions.contentblocker.enabled", True)
    options.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', False)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", 
                           "application/pdf, application/force-download")
    options.add_argument('--headless')
    driver = webdriver.Firefox(options=options)
    driver.install_addon(path=extension_path, temporary=True)
    driver.install_addon(path=extension_path2, temporary=True)
    driver.install_addon(path=extension_path3, temporary=True)

    

    try:
        driver.get(LinkToGet)
        print("SeleniumBrowser obtained News Link")   
    except Exception as error:
        print("SeleniumBrowser ran into an exception:", error)
        exit()
    driver.switch_to.window(driver.window_handles[0])


    def driverScriptsToExecute():
        driver.execute_script("""
        var element = document.querySelector(".css-103l8m3");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-3xqm5e");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-kzd6pg");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-13ldwoe");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1l8buln");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1n0orw4");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".evmxed20");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".e89cr9k1");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-sovreq");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1f2g8uf");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-7hsod0");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-d754w4");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1lpvp6o");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1xqucq6");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-gq7jix");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var element = document.querySelector(".css-1fdlqc e3rgvcb0");
        if (element)
        element.parentNode.removeChild(element);
        """)
        driver.execute_script("""
        var children =  document.querySelectorAll("div[id='fullBleedHeaderContent']");
        var childArray = Array.prototype.slice.call(children);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """)
        driver.execute_script("""
        var children =  document.querySelectorAll("div[data-testid='imageblock-wrapper']");
        var childArray = Array.prototype.slice.call(children);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """)
        driver.execute_script("""
        var children =  document.querySelectorAll("div[class='g-header-container g-theme-news g-align-center g-style-default svelte-1likblp']");
        var childArray = Array.prototype.slice.call(children);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """)
        driver.execute_script("""
        var children =  document.querySelectorAll("div[id='scrolly-instance-1']");
        var childArray = Array.prototype.slice.call(children);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """)

    driverScriptsToExecute()

    if LinkToGet.startswith("https://www.nytimes.com/interactive/"):
        driver.execute_script("""
        var element = document.querySelectorAll("figure");
        if (element)
        var childArray = Array.prototype.slice.call(element);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """)
    else:
        driver.execute_script("""
        var children =  document.querySelectorAll("section[data-testid='inline-interactive']");                         
        var childArray = Array.prototype.slice.call(children);
        childArray.forEach(function(child){
          child.parentNode.removeChild(child);})
        """) 


    
    try:
      RATIO_MULTIPLIER = 2.5352112676056335
      S = lambda X: driver.execute_script('return document.body.parentNode.scroll'+X)
      pdf_scaler = .01
      height = S('Height')
      weight = S('Width')
      print_options = PrintOptions()
      print_options.page_height = (height*pdf_scaler)*RATIO_MULTIPLIER
      print_options.page_width = (weight*pdf_scaler)*RATIO_MULTIPLIER
    except Exception as error:
        print("printing selenium ran into an exception:", error)
        exit()



    pdf = driver.print_page(print_options=print_options)
    if pdf == None:
        exit()
    else:
        pdf_bytes = base64.b64decode(pdf)
        with open("/home/site/wwwroot/seleniumOutput.pdf", "wb") as fh:                                   
            fh.write(pdf_bytes)


def convertPDF_To_txt():
    text = extract_text('/home/site/wwwroot/seleniumOutput.pdf', maxpages=1) 
    if text == None:
        exit()
    else:
        with open("/home/site/wwwroot/testoutput.txt", "a", encoding='utf-8') as file:
            file.write(text.replace("\n"," ").strip())

 
def RemoveUnexpectedHTML_Link_From_txt(LinkToGet):
    global indexesOfLinkContents
    indexesOfLinkContents = []
    global textToSummarize
    f = open("/home/site/wwwroot/testoutput.txt", "r", encoding='utf-8')
    textToSummarize = f.read()
    f.close()


    if textToSummarize == None:
        exit()

    else:
        if textToSummarize.startswith(LinkToGet):
            print("summary STARTS with a HTML LINK, summary NEEDS TO BE MODIFIED!!!!!!!!!!!!")
            indexesOfLinkContents = textToSummarize.split(LinkToGet)
        else:
            print("summary does NOT start with a HTML LINK, summary does NOT need to be modified")


def azureAI_AuthenticateClient():
    TA_credential = AzureKeyCredential(AZURE_COGNITIVE_KEY)
    text_analytics_client = TextAnalyticsClient(
            endpoint=AZURE_COGNITIVE_ENDPOINT, 
            credential=TA_credential)
    return text_analytics_client


def azureAI_NewsContentSummarization():
    global summaryToTweet
    summaryToTweet = None
    client = azureAI_AuthenticateClient()


    if indexesOfLinkContents != []:
        document = [
            unidecode(indexesOfLinkContents[-1])
        ]
    else:
        if textToSummarize == None:
            exit()
        else:
            document = [
                unidecode(textToSummarize)
            ]
    poller = client.begin_abstract_summary(document, sentence_count=5)
    abstract_summary_results = poller.result()
    for result in abstract_summary_results:
        if result.kind == "AbstractiveSummarization":
            summaryToTweet = result["summaries"][0]["text"]
            print("ABSTRACTIVE summary complete:")
            [print(f"{summary.text}\n") for summary in result.summaries]
        elif result.is_error is True:
            print("...Is an error with code '{}' and message '{}'".format(
                result.error.code, result.error.message
            ))
            poller = client.begin_extract_summary(document,max_sentence_count=6)                                                    #if the initial abstractive summary fails, fall back to an extractive summary instead
            document_results = poller.result()
            for result in document_results:
                extract_summary_result = result["sentences"][0]["text"]
                if result.is_error is True:
                    print("...Is an error with code '{}' and message '{}'".format(
                        extract_summary_result.code, extract_summary_result.message
                        ))
                else:
                    print("EXTRACTIVE summary complete since an ABSTRACTIVE one wasn't possible : \n{}".format(
                        " ".join([sentence.text for sentence in result.sentences]))
                    )                    
                    summaryToTweet = "{}".format(" ".join([sentence.text for sentence in result.sentences]))

    
    QNA_credential = AzureKeyCredential(AZURE_COGNITIVE_SEARCH_KEY)
    searchClient = QuestionAnsweringClient(AZURE_COGNITIVE_SEARCH_ENDPOINT, QNA_credential)
    listverContents = [summaryToTweet]

    with searchClient:
        question="Return to me the same exact text given but remove all the language issues from it Keep the same sentiment of the text including the main subject of the text Do not to include the names of the authors or the date of when the text was written" #Prompt is more effective when it is sloppy like shown
        output = searchClient.get_answers_from_text(question=question, text_documents=listverContents)
    print("unformatted ans:")
    print("Q: {}".format(question))
    print(output.answers[0].answer)
    summaryToTweet = output.answers[0].answer


def createPNGFromTXT():
    if summaryToTweet == None:
        exit()
    else:
        totalLengthOfImage = 0
        lines = textwrap.wrap(summaryToTweet, width=35, fix_sentence_endings=True)


        if summaryToTweet.endswith("."):
            print("summary ends with period, summary does NOT need to be modified")
        else:
            print("summary does NOT end with a period, summary NEEDS to be modified")
            indexesContainingPeriods = []

            for line in lines:
                if line.find(".") > -1:
                    indexesContainingPeriods.append(lines.index(line,0))

            if indexesContainingPeriods != []:
                lineThatEndsInPeriod = lines[indexesContainingPeriods[-1]].rsplit(".")
                while len(lines) != int(indexesContainingPeriods[-1]):
                    lines.pop()
                lines.append(lineThatEndsInPeriod[0] + ".")


        for line in lines:
           if len(lines) <= 3:
               totalLengthOfImage = totalLengthOfImage + 30
           elif len(lines) <= 6:
               totalLengthOfImage = totalLengthOfImage + 28
           elif len(lines) <= 9:
               totalLengthOfImage = totalLengthOfImage + 26
           elif len(lines) <= 12:
               totalLengthOfImage = totalLengthOfImage + 24
           elif len(lines) <= 15:
               totalLengthOfImage = totalLengthOfImage + 22
           elif len(lines) <= 18:
               totalLengthOfImage = totalLengthOfImage + 20
           else:
               totalLengthOfImage = totalLengthOfImage + 20

        font = ImageFont.truetype("PublicSans-Regular.otf", 18)
        img = Image.new('RGB', (350, totalLengthOfImage), (0, 0, 0))
        d = ImageDraw.Draw(img)


        if lines[-1].endswith("."):
            d.multiline_text((10, 10), '\n'.join(lines), fill=(255, 255, 255), align="left", spacing=1, font=font)
        else:
            print("No periods are found, setting default period placement!")
            d.multiline_text((10, 10), '\n'.join(lines) + ".", fill=(255, 255, 255), align="left", spacing=1, font=font)


        img.save("/home/site/wwwroot/MediaToTweet.png", 'png')


def summarizationFileDeletion():
    with os.scandir(path="/home/site/wwwroot/") as it:
        for entry in it:
            if entry.name.startswith('seleniumOutput.') and entry.is_file():
                print(entry.name)
                os.remove(entry)
            if entry.name.startswith('testoutput.') and entry.is_file():
                print(entry.name)
                os.remove(entry)
            if entry.name.startswith('MediaToTweet.') and entry.is_file():
                print(entry.name)
                os.remove(entry)
    print("The program has succesfully executed. Summarization Files from /tmp in the Linux OS have been deleted")


def makeTweetWithInsertedEntryInCosmosDB(datesToBeInsertedIntoDB,titlesToBeInsertedIntoDB,linksToBeInsertedIntoDB):
    if datesToBeInsertedIntoDB == []:
        print("This Should Never be Printed")
        return None
    
    print("Making Tweet")
    auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
    auth.set_access_token(ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)
    client = tweepy.Client(consumer_key = CONSUMER_KEY, consumer_secret = CONSUMER_SECRET, access_token = ACCESS_TOKEN, access_token_secret = ACCESS_TOKEN_SECRET)
    

    cleanedTweetDate = []                                                   #Removes timezone offset from the Tweet text
    cleanedDate = datesToBeInsertedIntoDB.replace(" +0000", "")
    cleanedTweetDate.append(cleanedDate)
    
    with tracer.start_as_current_span("STEP_FOUR_TWEET_RESPONSE") as span:
        if updatedLinks != [] and linksToBeInsertedIntoDB in updatedLinks:

            response = client.create_tweet(text = "At: " +cleanedTweetDate[0]+ "\n" "Article: " +matchedTitles[updatedLinks.index(linksToBeInsertedIntoDB)]+ "\nHad it's title updated to:\n" +titlesToBeInsertedIntoDB+  "\n" +linksToBeInsertedIntoDB+"")
            insertIntoCosmosDB(datesToBeInsertedIntoDB,titlesToBeInsertedIntoDB,linksToBeInsertedIntoDB)
            span.set_attribute("STEP_FOUR_TWEET_UPDATED_RESPONSE",f"{response}")
            span.set_attribute("STEP_FIVE_INSERTING_INTO_DB",f"{datesToBeInsertedIntoDB},{titlesToBeInsertedIntoDB},{linksToBeInsertedIntoDB}")

        else:
            print("Making a new/non-updated Tweet")                                                                             
            try:           
                seleniumfunction(linksToBeInsertedIntoDB)
            except Exception as error:
                span.record_exception(error) 
            try: 
                convertPDF_To_txt()
            except Exception as error:
                span.record_exception(error)
            try:
                RemoveUnexpectedHTML_Link_From_txt(linksToBeInsertedIntoDB)
            except Exception as error:
                span.record_exception(error) 
            try:
                azureAI_NewsContentSummarization()
            except Exception as error:
                span.record_exception(error)
            try: 
                createPNGFromTXT()
            except Exception as error:
                span.record_exception(error)

            media_path = "/home/site/wwwroot/MediaToTweet.png"
            try:
                uploaded_media = api.media_upload(media_path)
                summarizationFileDeletion()
                response = client.create_tweet(text = f"{cleanedDate},\n{titlesToBeInsertedIntoDB}\n{linksToBeInsertedIntoDB} ""Article summary below: \n", media_ids=[uploaded_media.media_id])
                span.set_attribute("STEP_FOUR_TWEET_NEW_RESPONSE",f"{response}")
                print(response)
                insertIntoCosmosDB(datesToBeInsertedIntoDB,titlesToBeInsertedIntoDB,linksToBeInsertedIntoDB)
                span.set_attribute("STEP_FIVE_INSERTING_INTO_DB",f"{datesToBeInsertedIntoDB},{titlesToBeInsertedIntoDB},{linksToBeInsertedIntoDB}")
            except Exception as error:
                print("An exception occured with the last tweet posting process:", error)


def deleteAllTxtFiles():
    with os.scandir(path="/home/site/wwwroot/") as it:
        for entry in it:
            if entry.name.startswith('MyFunction.') and entry.is_file():
                print(entry.name)
                os.remove(entry)
            if entry.name.startswith('MediaToTweet.') and entry.is_file():
                print(entry.name)
                os.remove(entry)
    print("The program has succesfully executed. Files from /tmp in the Linux OS have been deleted")
