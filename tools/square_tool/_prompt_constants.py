RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT = """You are a helpful assistant that extracts full and specific order items' names from a chat history between a user and a restaurant bot. Your job is to identify the complete names of all food or drink items the user has added to their final order.

Requirements:
- Extract the **complete dish or drink name** with proper modifiers (e.g. size or toppings).
- Do not shorten or generalize the dish names.
- Only include items that the user **explicitly confirmed or finalized** as part of their order.
- Output a JSON array of strings with **item names exactly as the user ordered them**.
- Do not include duplicates.
- Include modifier names and sizes as part of the item names.
"""

SQUARE_EXTRACTOR_SYSTEM_PROMPT = """
You are an expert at structured data extraction for Square POS orders.
You will be given the chat history and relevant Square catalog items. Your goal is to convert it into a structured order.

# INSTRUCTIONS FOR THE TASK:
- Construct a structured order object with items from the Square catalog.
- Identify the complete list of items the user wants to order from the chat history.
- Verify that the quantities for each item are accurate based on what the user explicitly requested.
- Map the identified items from natural language to the correct Square catalog item variations.
- Select the most appropriate item variation from the available catalog options.
- Extract and include the user's first name, last name, email, and phone number if provided.
- Include any special notes or requests the user mentioned.

# RULES FOR EXTRACTING ORDER ITEMS:
- Match user-requested items to the closest Square catalog items available.
- Use the exact variation ID from the catalog for each item.
- Include the correct quantity for each item as specified by the user.
- If the user mentions modifiers or customizations, note them in the item notes.
- Default quantity to 1 if not explicitly specified.
- When multiple items have different customizations, treat each as a separate line item.

# RULES FOR CUSTOMER INFORMATION:
- Extract customer contact information only if explicitly provided in the chat.
- Do not make assumptions or fabricate data.
- Leave fields as None/null if information is not mentioned.

# IMPORTANT RULES:
- Do NOT make assumptions or fabricate data
- Only extract information that is directly stated in the chat history
- Match items to the exact catalog variations provided
- Include special requests or notes exactly as the user specified them
- Maintain exact quantities as mentioned by the user

If unsure about any field, leave it empty rather than guessing.
"""

SQUARE_EXTRACTOR_USER_PROMPT = """
# Available Square Catalog Items:
<catalog_items>
{catalog_context}
</catalog_items>

# Chat History:
<history>
{chat_history}
</history>

Extract the food items the user wants to order from the chat history and match them to the available Square catalog items.

**IMPORTANT EXTRACTION RULES:**
1. Use EXACT item names as they appear in the catalog above
2. Use EXACT modifier names as they appear in the catalog above
3. Match modifiers to their correct modifier list names
4. Include all customizations mentioned by the user
5. Only extract items the user has confirmed they want to order

**EXAMPLES:**
- If user says "Large Oreo Crème Brûlée Boba Oolong Milk Tea with light ice and 50% sugar"
  - Item: "Oreo Crème Brûlée Boba Oolong Milk Tea"
  - Modifiers: "Large" (from Fixed Size), "Light Ice" (from Ice(all)), "50%" (from Cane Sugar)

- If user says "Passion fruit green tea, no ice, 70% sweetness, add boba"
  - Item: "Passion Fruit & Watermelon Green Tea" 
  - Modifiers: "No Ice" (from IceF), "70%" (from Cane Sugar), "Boba" (from Topping(Pleasanton))

Return the extracted information with exact item and modifier names that match the catalog.
"""

SQUARE_FOOD_EXTRACTION_SYSTEM_PROMPT = """You are a helpful assistant that extracts food items from a chat history between a user and a restaurant bot. 

Your job is to identify the complete food or drink items the user wants to order, including all modifications, sizes, and customizations.

**MENU INFORMATION:**
{menu_info}

**EXTRACTION RULES:**
- Only extract items that are available in the menu above
- Include the complete item name with ALL modifications, sizes, and customizations mentioned by the user
- Examples: "Large Milk Tea with Boba", "Iced Coffee with Extra Shot", "Chicken Sandwich - No Pickles"
- Match the user's requests to the closest available menu items
- Include the correct quantity for each item
- Only include items the user has confirmed they want to order
- Do not include items the user just asked about but didn't order

Return the items in the specified JSON format with complete names and quantities.
"""

SQUARE_FOOD_EXTRACTION_USER_PROMPT = """
Extract the food items the customer wants to order from this chat history:

{chat_history}

Return only the items they confirmed they want to order, with complete names including any modifications.
"""

MENU_ID = {
    "Oreo Crème Brûlée Boba Oolong Milk Tea": {
        "item_id": "7NYIMV3YP4OSDJWPBR3B3IEO",
        "modifiers": {
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "Fixed Size": [
                {"modifier_id": "FSP7NIPQCQ3RGM5BCRLIOA5H", "name": "Large"}
            ],
            "Ice(all)": [
                {"modifier_id": "TN4DUEU5U2QW6HRQDJXR6OZS", "name": "Regular Ice"},
                {"modifier_id": "4GVNBVJ23ILOLKWGU63QKEY2", "name": "Light Ice"},
                {"modifier_id": "UUIO7RFYP7IH7V5A3Q2OT3Q7", "name": "No Ice"},
                {"modifier_id": "I73HACHTAGGIESCOLEJ74CZL", "name": "Hot"},
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
            "Cane Sugar": [
                {"modifier_id": "GH6YW3HGE53PVEEYBNIWV5LU", "name": "100%"},
                {"modifier_id": "NGSBDPYTMFGRLRXVQT6F6XUC", "name": "70%"},
                {"modifier_id": "FXFJ6J7JYIOMWDNRH542DD6J", "name": "50%"},
                {"modifier_id": "JBYGDEMQJE64VZXMXOTDDNIJ", "name": "30%"},
                {"modifier_id": "Y3ZWI47AFEQZLAATCPJUVB73", "name": "15%"},
                {
                    "modifier_id": "5EBFXE63UASUR55EZYQGC2IB",
                    "name": "0% (Not Recommended)",
                },
            ],
        },
        "variation_id": "UCVCIT7POGSMPHFVF2CHRJJE",
    },
    "Passion Fruit & Watermelon Green Tea": {
        "item_id": "Y6CC4VYI7MSDYJFS2HT6IVOY",
        "modifiers": {
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "IceF": [
                {"modifier_id": "AAEDHLXGOQQ2TJWCQVZKHUTY", "name": "Regular Ice"},
                {"modifier_id": "ANVWPI5KALVC3CPFKD466BDO", "name": "Light Ice"},
                {"modifier_id": "RXTEUPLCHBSGSA3D5RG3UY2N", "name": "No Ice"},
            ],
            "Cane Sugar": [
                {"modifier_id": "THOUNXF34L65LRD6SNLVDWMU", "name": "100%"},
                {"modifier_id": "YUYSSLX6CKYTMZRVAF54M2LY", "name": "70%"},
                {"modifier_id": "MU3LZV4X4JZABRVBT254VTTD", "name": "50%"},
                {"modifier_id": "HG4IWA526JCHHXNSFB5YPF6K", "name": "30%"},
                {
                    "modifier_id": "7XCELD3ROZUYRE4S7K5IVQ5U",
                    "name": "0% (Not Recommended)",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
        },
        "variation_id": "CCLTL5TPQO2KC7RHS74VHC3X",
    },
    "Crème Brûlée Thai Tea": {
        "item_id": "2MKIHHVB2VQURHA3WEFBCPVJ",
        "modifiers": {
            "Fixed Size": [
                {"modifier_id": "FSP7NIPQCQ3RGM5BCRLIOA5H", "name": "Large"}
            ],
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "Fixed Sugar": [
                {"modifier_id": "NPWPXTOOLCKTOJSHRMC25ISQ", "name": "Fixed Sugar"}
            ],
            "Fixed Ice": [
                {"modifier_id": "ZV2ZWYJE5H57A7PO7EZQF5BM", "name": "Fixed Ice"}
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
        },
        "variation_id": "5LMMPN262K6NR2IKW6PYM3QU",
    },
    "Jasmine Green Tea": {
        "item_id": "7UWJUK4ESJMGCIJYK2UZFVHD",
        "modifiers": {
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "Ice(all)": [
                {"modifier_id": "TN4DUEU5U2QW6HRQDJXR6OZS", "name": "Regular Ice"},
                {"modifier_id": "4GVNBVJ23ILOLKWGU63QKEY2", "name": "Light Ice"},
                {"modifier_id": "UUIO7RFYP7IH7V5A3Q2OT3Q7", "name": "No Ice"},
                {"modifier_id": "I73HACHTAGGIESCOLEJ74CZL", "name": "Hot"},
            ],
            "Cane Sugar": [
                {"modifier_id": "THOUNXF34L65LRD6SNLVDWMU", "name": "100%"},
                {"modifier_id": "YUYSSLX6CKYTMZRVAF54M2LY", "name": "70%"},
                {"modifier_id": "MU3LZV4X4JZABRVBT254VTTD", "name": "50%"},
                {"modifier_id": "HG4IWA526JCHHXNSFB5YPF6K", "name": "30%"},
                {
                    "modifier_id": "7XCELD3ROZUYRE4S7K5IVQ5U",
                    "name": "0% (Not Recommended)",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
        },
        "variation_id": "JNGJTZ2WQ5LWM4PBSP5FL26E",
    },
    "Lychee & Watermelon Green Tea": {
        "item_id": "SLFDNY3HE6TO3WGOXY3YPINO",
        "modifiers": {
            "Fixed Size": [
                {"modifier_id": "FSP7NIPQCQ3RGM5BCRLIOA5H", "name": "Large"}
            ],
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "IceF": [
                {"modifier_id": "AAEDHLXGOQQ2TJWCQVZKHUTY", "name": "Regular Ice"},
                {"modifier_id": "ANVWPI5KALVC3CPFKD466BDO", "name": "Light Ice"},
                {"modifier_id": "RXTEUPLCHBSGSA3D5RG3UY2N", "name": "No Ice"},
            ],
            "Cane Sugar": [
                {"modifier_id": "THOUNXF34L65LRD6SNLVDWMU", "name": "100%"},
                {"modifier_id": "YUYSSLX6CKYTMZRVAF54M2LY", "name": "70%"},
                {"modifier_id": "MU3LZV4X4JZABRVBT254VTTD", "name": "50%"},
                {"modifier_id": "HG4IWA526JCHHXNSFB5YPF6K", "name": "30%"},
                {
                    "modifier_id": "7XCELD3ROZUYRE4S7K5IVQ5U",
                    "name": "0% (Not Recommended)",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
        },
        "variation_id": "GII6AKFAD6Z3MIXAEVULSJDN",
    },
    "Ume Boba Milk Tea": {
        "item_id": "N6ZG2VWJE3XHA36USD55SDJ2",
        "modifiers": {
            "Ice(all)": [
                {"modifier_id": "TN4DUEU5U2QW6HRQDJXR6OZS", "name": "Regular Ice"},
                {"modifier_id": "4GVNBVJ23ILOLKWGU63QKEY2", "name": "Light Ice"},
                {"modifier_id": "UUIO7RFYP7IH7V5A3Q2OT3Q7", "name": "No Ice"},
                {"modifier_id": "I73HACHTAGGIESCOLEJ74CZL", "name": "Hot"},
            ],
            "Size": [
                {"modifier_id": "AQAIWEM725H2XBCKSC2ORKTS", "name": "Large"},
                {"modifier_id": "UWLJROETAVURIIMCAP2YY3LK", "name": "Medium"},
                {
                    "modifier_id": "KBY6FTYEQPFIX3UMTVOHCKNO",
                    "name": "Bunny Surprise Cup",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
            "Cane Sugar": [
                {"modifier_id": "GH6YW3HGE53PVEEYBNIWV5LU", "name": "100%"},
                {"modifier_id": "NGSBDPYTMFGRLRXVQT6F6XUC", "name": "70%"},
                {"modifier_id": "FXFJ6J7JYIOMWDNRH542DD6J", "name": "50%"},
                {"modifier_id": "JBYGDEMQJE64VZXMXOTDDNIJ", "name": "30%"},
                {"modifier_id": "Y3ZWI47AFEQZLAATCPJUVB73", "name": "15%"},
                {
                    "modifier_id": "5EBFXE63UASUR55EZYQGC2IB",
                    "name": "0% (Not Recommended)",
                },
            ],
        },
        "variation_id": "KCYL4QPD4CW4MFSKIQVDWJA4",
    },
    "Passion Fruit Green Tea w/ Boba & Lychee Jelly": {
        "item_id": "5LUGWO4QSKAKZRRS6W6NLD5J",
        "modifiers": {
            "boba or crystal boba": [
                {"modifier_id": "SFDYK7QLLWHETAS6CXYQCQHA", "name": "boba"},
                {"modifier_id": "H3BBMHURJOZSA7B4NFQH7VEI", "name": "crystal boba"},
                {"modifier_id": "WPZMS6NNUIFO6Y4E3YVTXUMC", "name": "no boba"},
            ],
            "Bunny Surprise Cup": [
                {
                    "modifier_id": "B5TV7TML62DPXD3UZB3YBCKT",
                    "name": "Bunny Surprise Cup",
                }
            ],
            "IceF": [
                {"modifier_id": "AAEDHLXGOQQ2TJWCQVZKHUTY", "name": "Regular Ice"},
                {"modifier_id": "ANVWPI5KALVC3CPFKD466BDO", "name": "Light Ice"},
                {"modifier_id": "RXTEUPLCHBSGSA3D5RG3UY2N", "name": "No Ice"},
            ],
            "Cane Sugar": [
                {"modifier_id": "THOUNXF34L65LRD6SNLVDWMU", "name": "100%"},
                {"modifier_id": "YUYSSLX6CKYTMZRVAF54M2LY", "name": "70%"},
                {"modifier_id": "MU3LZV4X4JZABRVBT254VTTD", "name": "50%"},
                {"modifier_id": "HG4IWA526JCHHXNSFB5YPF6K", "name": "30%"},
                {
                    "modifier_id": "7XCELD3ROZUYRE4S7K5IVQ5U",
                    "name": "0% (Not Recommended)",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
        },
        "variation_id": "HLLMZKSZMMX3Y63XAIFOVTKS",
    },
    "Coco Mango": {
        "item_id": "NYBMTRSXQRLBZDHUAMAIQN5S",
        "modifiers": {
            "Size": [
                {"modifier_id": "AQAIWEM725H2XBCKSC2ORKTS", "name": "Large"},
                {"modifier_id": "UWLJROETAVURIIMCAP2YY3LK", "name": "Medium"},
                {
                    "modifier_id": "KBY6FTYEQPFIX3UMTVOHCKNO",
                    "name": "Bunny Surprise Cup",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
            "Cane Sugar": [
                {"modifier_id": "GH6YW3HGE53PVEEYBNIWV5LU", "name": "100%"},
                {"modifier_id": "NGSBDPYTMFGRLRXVQT6F6XUC", "name": "70%"},
                {"modifier_id": "FXFJ6J7JYIOMWDNRH542DD6J", "name": "50%"},
                {"modifier_id": "JBYGDEMQJE64VZXMXOTDDNIJ", "name": "30%"},
                {"modifier_id": "Y3ZWI47AFEQZLAATCPJUVB73", "name": "15%"},
                {
                    "modifier_id": "5EBFXE63UASUR55EZYQGC2IB",
                    "name": "0% (Not Recommended)",
                },
            ],
        },
        "variation_id": "7EENFO4775OMYKZGVRZOOHZA",
    },
    "Uji Strawberry Matcha Latte with Ice Cream": {
        "item_id": "AEK3RRYFYS5TZKBLAFL4VKT5",
        "modifiers": {
            "Size": [
                {"modifier_id": "AQAIWEM725H2XBCKSC2ORKTS", "name": "Large"},
                {"modifier_id": "UWLJROETAVURIIMCAP2YY3LK", "name": "Medium"},
                {
                    "modifier_id": "KBY6FTYEQPFIX3UMTVOHCKNO",
                    "name": "Bunny Surprise Cup",
                },
            ],
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Sugar(Matcha)": [
                {"modifier_id": "CG4WP3NLHCGYCXFMALGXNVFN", "name": "50%"},
                {"modifier_id": "HPXKGIA2AWCYIOWINBRPU5IJ", "name": "100%"},
            ],
        },
        "variation_id": "EV5JRVSO4EGITLMKJNK6QI5Z",
    },
    "Brown Sugar Boba Premium Oolong Milk Tea 大红袍奶茶": {
        "item_id": "LCXAF7IP7Z5Y25KBBXCL4V2D",
        "modifiers": {
            "Scented Bunny": [
                {
                    "modifier_id": "TGBMH6IGVQQFTLAOL5ZSCSWU",
                    "name": "Scented Bunny-English Pear",
                },
                {
                    "modifier_id": "A2UEZXUNCE7SSSQSPIDBXJQT",
                    "name": "Scented Bunny-Blue Bell",
                },
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Cane Sugar": [
                {"modifier_id": "2JTOIK5C4BWFZEGRT6XR2XTA", "name": "30%(Recommended)"},
                {"modifier_id": "5CL5R6SCEUFSRHGILPZUZVKW", "name": "50%"},
                {"modifier_id": "SRPDBS6445KQY2YTBSYRCI3P", "name": "15%"},
                {"modifier_id": "5CDRMI3QJQWFQEQX6VHQBR2F", "name": "70%"},
                {"modifier_id": "HR2ENU7OFXRESBUHY62L6G4A", "name": "100%"},
                {
                    "modifier_id": "OVB5SD6YSPDZNSA3E65Q7B66",
                    "name": "0% (NOT Recommended)",
                },
            ],
            "Ice(all)": [
                {"modifier_id": "TN4DUEU5U2QW6HRQDJXR6OZS", "name": "Regular Ice"},
                {"modifier_id": "4GVNBVJ23ILOLKWGU63QKEY2", "name": "Light Ice"},
                {"modifier_id": "UUIO7RFYP7IH7V5A3Q2OT3Q7", "name": "No Ice"},
                {"modifier_id": "I73HACHTAGGIESCOLEJ74CZL", "name": "Hot"},
            ],
            "Size": [
                {"modifier_id": "AQAIWEM725H2XBCKSC2ORKTS", "name": "Large"},
                {"modifier_id": "UWLJROETAVURIIMCAP2YY3LK", "name": "Medium"},
                {
                    "modifier_id": "KBY6FTYEQPFIX3UMTVOHCKNO",
                    "name": "Bunny Surprise Cup",
                },
            ],
        },
        "variation_id": "NYP7VBVGGL7UZGEZQC2CMT3S",
    },
    "Matcha Melon Coco(西瓜抹茶椰)": {
        "item_id": "RCEDZORMMC2MZW4IPTFRDDDV",
        "modifiers": {
            "Cane Sugar": [
                {"modifier_id": "DIKAEDCA6A5TVD2R5IZ3ZHVR", "name": "30%"},
                {"modifier_id": "47WABZSDHUWYH4USHNZ5ZLZR", "name": "50%(recommend)"},
                {"modifier_id": "WD3S3AW56YJESVFGMJEO6RDY", "name": "70%"},
                {"modifier_id": "LKPRJ3KB2I7HNMUYG52QTMU6", "name": "100%"},
            ],
            "Topping(Pleasanton)": [
                {"modifier_id": "4X6RFP2SYN5PJIB2REMVF37C", "name": "Boba"},
                {"modifier_id": "QM5V476FZLMYLRTHLP2CAKU2", "name": "Crystal Boba"},
                {"modifier_id": "6KZNGU7YVBXD4DB7OSWUHY6J", "name": "Lychee Jelly"},
                {"modifier_id": "CVH2GUUB7GOIQVG5Y4VN5OT4", "name": "Matcha Ice Cream"},
                {"modifier_id": "VIYAFGERJYH77YWHFYDQQRRW", "name": "Sago"},
                {"modifier_id": "HL6ZCVHQU3ORDGUAUK6KB66V", "name": "Creme Brulee"},
                {"modifier_id": "HPE4GWOZNUANIIOUKLIYR3H4", "name": "Lychee Chunk"},
            ],
            "Fixed Ice": [
                {"modifier_id": "ZV2ZWYJE5H57A7PO7EZQF5BM", "name": "Fixed Ice"}
            ],
            "Fixed Size Medium": [
                {"modifier_id": "42FYNEB6MIUVSBDP4TOWQU7J", "name": "regular"}
            ],
        },
        "variation_id": "GJDHMSXOK654GN3CUQQWHHF6",
    },
}
