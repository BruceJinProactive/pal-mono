from llama_index.core import Document, VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.llamaindex import LlamaIndexKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

import db
from agent.config import KnowledgeConfig, KnowledgeProvider
from agent.model import get_embedder

fall_features = """### Fall Features
1. **Vanilla Date Delight**: Cold Brew Coffee with vanilla, all-natural date syrup, cinnamon, and oat milk.
2. **Spiced Vanilla Soul**: Cold Brew Coffee with house-made spiced oat milk, and vanilla."""

iced_coffee = """### Iced Coffee
1. **Mint Cassandra**: Fresh Mint, Sweet, Creamy.
2. **Gingersnap**: Spices, Sweet, Creamy.
3. **Citrus Delight**: Butterscotch, Dark Chocolate, Citrus.
4. **Iced Coffee Rosé**: Rose, Sweet, Creamy.
5. **Epic Cold Brew Coffee**: Milk Chocolate, Dried Berry, Almond.
6. **Cold Brew Coffee**: Hazelnut, Maple, Caramel.
7. **Honey Haze**: Cold Brew Coffee with Honey and Oat Milk.
8. **Oatmeal Cookie Cold Brew Coffee**: Epic Cold Brew Coffee with cinnamon and oat milk."""

dark_roast = """### Dark Roast Coffee
1. **Tantalizing Turkish**: Aromatic Arabic Blend, Cardamom, Mint.
2. **Ether**: Molasses, Dried Cherry, Dark Chocolate.
3. **Aromatic Arabic**: Toffee, Cedar, Smoke.
4. **Almond Biscotti**: Dark Chocolate, Almond, Berry, Smoke."""

medium_roast = """### Medium Roast Coffee
1. **Silken Splendor**: Toffee, Chocolate, Citrus.
2. **Ultimate Delight**: Berry, Fudge, Molasses.
3. **New England Hazelnut**: Hazelnut Flavoring, Maple, Caramel.
4. **Cardamom Cinnamon**: Cardamom, Cinnamon, Honey."""

light_roast = """### Light Roast Coffee
1. **Biscuit Citrus**: Brown Sugar, Biscuit, Citrus.
2. **Berry Hibiscus**: Milk Chocolate, Dried Berry, Hibiscus.
3. **Honey Bear**: Honey, Citrus, Graham Cracker."""

decaf = """### Decaf
1. **B Street Unplugged Decaf**: Chocolate, Nuts, Raisin."""

sandwiches = """### Breakfast Sandwiches
1. **Green Chile Burrito**: A hearty green chile burrito with eggs, potatoes, and cheese.
2. **Bacon & Egg Burrito**: Flour tortilla, eggs, potatoes, cheddar cheese, and crispy bacon.
3. **Pork Sausage & Egg Burrito**: Flour tortilla, eggs, potatoes, cheddar cheese, and pork sausage.
4. **Turkey Sausage Sandwich**: A toasted English muffin, scrambled egg patty, turkey sausage, and jalapeño pepper jack cheese.
5. **B Street Vegan Sandwich**: A 100% plant-based meal! Made with Beyond Meat®, JUST Egg and Daiya Cheese."""

croissants = """### Croissants
1. **Butter Croissant**: An all-butter recipe, layered and folded for a light, flaky croissant.
2. **Chocolate Croissant**: A light airy pastry layered around dark chocolate.
3. **Twice Baked Almond Croissant**: Tasty buttery croissant with almond filling and covered in toasted almonds.
4. **Bacon & Onion Pretzel Croissant**: A layered pretzel dough with bacon, caramelized onions, porcini mushrooms, topped with poppy seeds and Swiss cheese."""

muffins = """### Muffins
1. **Bran Muffin**: A hearty muffin made with wheat bran, barley flour, honey, and molasses.
2. **Blueberry Muffin**: Buttery, moist blueberry muffin made with buttermilk."""

anna_knowledge = [
    fall_features,
    iced_coffee,
    dark_roast,
    medium_roast,
    light_roast,
    decaf,
    sandwiches,
    croissants,
    muffins,
]


def get_knowledge(config: KnowledgeConfig) -> AgentKnowledge:
    if config.provider == KnowledgeProvider.LLAMAINDEX:
        # Use llamaindex
        documents = [Document(text=t) for t in anna_knowledge]
        index = VectorStoreIndex.from_documents(documents)
        retriever = VectorIndexRetriever(index)
        knowledge = LlamaIndexKnowledgeBase(retriever=retriever)
    elif config.provider == KnowledgeProvider.DEFAULT:
        # Use phidata's combined knowledge base
        knowledge_table_name = f"{config.identifier}_knowledge"
        knowledge = CombinedKnowledgeBase(
            sources=[],
            vector_db=PgVector2(
                db_url=db.db_url,
                collection=knowledge_table_name,
                embedder=get_embedder(),
            ),
            # 2 references are added to the prompt
            num_documents=10,
        )
    else:
        raise ValueError(f"Unknown provider: {config.provider}")

    return knowledge
