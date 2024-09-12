from fastapi import FastAPI
from pydantic import BaseModel
class Item(BaseModel):
    name: str


app = FastAPI()


class customItem(BaseModel):
    name: list[str] = []



@app.put("/items/Function1Output")
async def update_item(item: Item):
    global Function1Output
    Function1Output = item.name
    return item.model_dump()

@app.get("/items/Function1Output")
async def step2():
    results = Function1Output
    return results



@app.put("/items/CountEntriesInXML")
async def update_item(item: Item):
    global CountEntriesInXML
    CountEntriesInXML = item.name
    return item.model_dump()
@app.get("/items/CountEntriesInXML")
async def step2():
    results = CountEntriesInXML
    return results






@app.put("/items/ItemsToFindFromFunc3")
async def update_item(item: Item):
    global ItemsToFindFromFunc3
    ItemsToFindFromFunc3 = item.name
    return item.model_dump()

@app.get("/items/ItemsToFindFromFunc3")
async def step2():
    results = ItemsToFindFromFunc3
    return results






@app.put("/items/LinksToFindFromFunc4")
async def update_item(customItem: customItem):
    global LinksToFindFromFunc4
    LinksToFindFromFunc4 = customItem.name
    return customItem.model_dump()
@app.put("/items/DatesToFindFromFunc4")
async def update_item(customItem: customItem):
    global DatesToFindFromFunc4
    DatesToFindFromFunc4 = customItem.name
    return customItem.model_dump()
@app.put("/items/TitlesToFindFromFunc4")
async def update_item(customItem: customItem):
    global TitlesToFindFromFunc4
    TitlesToFindFromFunc4 = customItem.name
    return customItem.model_dump()




@app.get("/items/TitlesToFindFromFunc4")
async def step2():
    results = TitlesToFindFromFunc4
    return results
@app.get("/items/LinksToFindFromFunc4")
async def step2():
    results = LinksToFindFromFunc4
    return results
@app.get("/items/DatesToFindFromFunc4")
async def step2():
    results = DatesToFindFromFunc4
    return results



@app.put("/items/DatesToInsert")
async def update_item(customItem: customItem):
    global DatesToInsert    
    DatesToInsert = customItem.name
    return customItem.model_dump()
@app.put("/items/LinksToInsert")
async def update_item(customItem: customItem):
    global LinksToInsert   
    LinksToInsert = customItem.name
    return customItem.model_dump()
@app.put("/items/TitlesToInsert")
async def update_item(customItem: customItem):
    global TitlesToInsert
    TitlesToInsert = customItem.name
    return customItem.model_dump()




@app.get("/items/TitlesToInsert")
async def step2():
    results = TitlesToInsert
    return results
@app.get("/items/DatesToInsert")
async def step2():
    results = DatesToInsert
    return results 
@app.get("/items/LinksToInsert")
async def step2():
    results = LinksToInsert
    return results 

