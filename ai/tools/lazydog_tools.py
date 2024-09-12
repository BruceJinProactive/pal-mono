import random

from phi.tools import Toolkit


class LazyDogTools(Toolkit):
    def __init__(self):
        super().__init__(name="lazyDog_Tools")
        self.register(self.get_beer_club_surprise)
        self.register(self.get_campfire_community_surprise)
        self.register(self.get_campfire_club_surprise)
        self.register(self.get_birthday_surprise_beer_club)
        self.register(self.get_birthday_surprise_campfire_community)
        self.register(self.get_birthday_surprise_campfire_club)
        self.register(self.get_seasonal_special_food)
        self.register(self.get_tv_dinner)

    """
    Tools for the LazyDogTools class.
    
    Commands for the LazyDog Tools:
    - $BEERCLUB_SURPRISE_$: Get a surprise event for members of the Lazy Dog beer club.
    - $CAMPFIRE_SURPRISE_$: Get a surprise event for members of the Lazy Dog Campfire Community.
    - $CAMPFIRECLUB_SURPRISE_$: Get a surprise event for members of the Lazy Dog Campfire Club.
    - $BIRTHDAY_SURPRISE_BEER_$: Get a surprise event for members of the Lazy Dog beer club celebrating their birthday.
    - $BIRTHDAY_SURPRISE_CAMPFIRE_COMMUNITY_$: Get a surprise event for members of the Lazy Dog Campfire Community celebrating their birthday.
    - $BIRTHDAY_SURPRISE_CAMPFIRE_CLUB_$: Get a surprise event for members of the Lazy Dog Campfire Club celebrating their birthday.
    """

    def get_beer_club_surprise(self):
        """This function retrieves and returns information about a surprise event for Lazy Dog Beer Club members.

        **Instructions:**

        - Trigger this function only when the user enters the exact phrase: "$BEERCLUB_SURPRISE_$".
        - Do not call the function in any other scenario unless the user explicitly mentions they are a Lazy Dog Beer Club member.
        - Ensure that the user is a club member before calling the function in contexts where club membership is mentioned.
        """

        surprise = [
            """Brewery Collaboration VIP Experience
Description: Members get exclusive invites to visit one of the collaborating breweries for a behind-the-scenes tour. Includes meet-and-greet sessions with brewmasters, hands-on brewing experience, and exclusive beer tastings of unreleased brews.
Frequency: Twice a year (aligned with quarterly beer kit releases).
Surprise Element: A surprise limited-edition beer bottle from the event with personalized labels.""",
            """Beer & Food Pairing Masterclass
Description: An online or in-person class hosted by a renowned chef and a master brewer to teach members about pairing craft beers with gourmet dishes. Includes a curated food kit and beer sampler for virtual events.
Frequency: Once per quarter.
Surprise Element: Members who attend get a curated take-home meal kit and a discount on the next beer kit.""",
            """Surprise Seasonal Beer Releases
Description: Unannounced seasonal or holiday-themed beers delivered to Beer Club members as part of their regular kit. These special brews would be crafted with unique, festive flavors.
Surprise Element: A holiday-themed beer glass included, designed exclusively for members.""",
            """ Beer Olympics
Description: An in-person or virtual event where Beer Club members compete in fun, beer-related challenges such as blind beer tasting, trivia, and keg toss. Winners receive special beer-related gear or a free quarter's worth of membership.
Frequency: Annually during summer.
Surprise Element: Winners of each challenge get a year-long feature on the Beer Club’s wall of fame.""",
        ]
        # randomly select a surprise event
        return random.choice(surprise)

    def get_campfire_community_surprise(self):
        """This function provides information about a surprise event for members of the Lazy Dog Campfire Community.

        **Instructions:**

        - Invoke this function only when the user inputs the exact phrase: "$CAMPFIRE_SURPRISE_$" in the chat.
        - Do not trigger this function under any other circumstances unless the user has clearly indicated they are a member of the Lazy Dog Campfire Community.
        - Ensure the user's membership in the Campfire Community is explicitly mentioned or verified before calling the function.
        """

        surprise = [
            """Campfire Cookout Nights
Description: A family-friendly outdoor event at select Lazy Dog locations where members enjoy a complimentary cookout. This includes marshmallow roasting, live acoustic music, and outdoor games.
Frequency: Every summer.
Surprise Element: Members receive a limited-edition Lazy Dog branded campfire mug as a gift.""",
            """Secret Menu Days
Description: Campfire Community members get access to a secret menu for one day each quarter. This menu will include exclusive dishes and off-the-menu cocktails or appetizers.
Surprise Element: Members are given a special keychain that grants them access to all future secret menu days.""",
            """Community Volunteering Day
Description: A day where Lazy Dog partners with local organizations to set up a community volunteering event. Members can join in charitable activities such as park cleanups or food drives, followed by an appreciation lunch.
Frequency: Twice a year (spring and fall).
Surprise Element: Each member who participates receives a custom Lazy Dog "Community Hero" t-shirt and a certificate for a free meal.""",
            """Exclusive Movie Nights
Description: Outdoor movie screenings at select Lazy Dog locations, featuring family-friendly films or classic movies. Members get free popcorn, s'mores kits, and blankets to enjoy during the screening.
Frequency: Once a season.
Surprise Element: Every movie night offers a chance to win a Lazy Dog gift card, with surprise giveaways during the event.""",
        ]

        # randomly select a surprise event
        return random.choice(surprise)

    def get_campfire_club_surprise(self):
        """This function provides information about a surprise event exclusively for members of the Lazy Dog Campfire Club.

        **Instructions**:
        - Trigger this function **only** when the user enters the exact phrase: **"$CAMPFIRECLUB_SURPRISE_$"** in the chat.
        - Do **not** call this function in any other situation unless the user explicitly confirms they are a member of the Lazy Dog Campfire Club.
        - Ensure that the user's membership in the Campfire Club is mentioned or validated before invoking the function.
        """

        surprise = [
            """Exclusive Chef’s Table Dinners
Description: Campfire Club members are invited to a private, multi-course tasting dinner hosted by Lazy Dog’s executive chef. Each course is paired with a drink, and members get the chance to give input on future menu items.
Frequency: Twice a year.
Surprise Element: At the end of the dinner, members receive a personalized, signed recipe book featuring the dishes served.""",
            """Campfire Adventure Box
Description: A quarterly surprise box delivered to members, featuring adventure-themed items like a travel journal, camping gear (e.g., pocketknife, outdoor lantern), and unique Lazy Dog recipes designed for campfire cooking.
Frequency: Quarterly.
Surprise Element: One random member per quarter receives a fully-paid weekend camping trip package for two.""",
            """Mixology Masterclass
Description: An exclusive event where Campfire Club members learn to create Lazy Dog’s signature cocktails. Includes hands-on demonstrations by professional mixologists, with members receiving an at-home cocktail kit.
Frequency: Bi-annual.
Surprise Element: Attendees receive a personalized cocktail shaker with their name engraved.""",
            """Private Campfire Music Sessions
Description: Private live music sessions at select Lazy Dog locations featuring local indie musicians. Members get exclusive access to these intimate performances with complimentary drinks and appetizers.
Frequency: Monthly.
Surprise Element: A surprise CD or digital download of the performing artist’s music, signed by the musician.""",
        ]

        # randomly select a surprise event
        return random.choice(surprise)

    def get_birthday_surprise_beer_club(self):
        """This function returns information about a birthday surprise event specifically for members of the Lazy Dog Beer Club.

        **Instructions**:
        - Invoke this function **only** when the user inputs the exact phrase: **"$BIRTHDAY_SURPRISE_BEER_$"** in the chat.
        - Do **not** call this function in any other situation unless the user explicitly confirms both their membership in the Lazy Dog Beer Club and that they are celebrating their birthday.
        - Ensure both the user's club membership and birthday celebration are clearly mentioned or confirmed before triggering the function.
        """

        beer_surprise = [
            """Birthday Beer Bash
Description: Members receive an exclusive invite to celebrate their birthday with a complimentary Birthday Beer Flight at their home Lazy Dog location. The flight includes a selection of rare and seasonal brews curated just for their special day.
Surprise Element: The member's name and birthday are featured on the "Birthday Brewmasters Board" in the restaurant for the month, and they receive a custom Lazy Dog birthday pint glass to take home.""",
            """Personalized Birthday Brew
Description: For Beer Club members, Lazy Dog offers a personalized beer label for their birthday. The birthday member can pick a beer from the current lineup, and Lazy Dog will provide a bottle or can with a custom label featuring the member's name, birthdate, and a personal message.
Surprise Element: The label design is a surprise, featuring artwork based on the member’s zodiac sign or their favorite beer type.""",
            """Brewery Birthday Tour and Tasting
Description: On their birthday month, members receive a free pass for a VIP tour and tasting session at a collaborating local brewery. This includes an exclusive tour of the brewery's facilities, tastings of newly released brews, and a behind-the-scenes look at their brewing process.
Surprise Element: Members get to take home a limited-edition birthday beer created specially for the month, available only to birthday celebrants.""",
        ]

        # randomly select a surprise event
        return f"The user is celebrating their birthday today! Here's a special surprise event for them: \n\n{random.choice(beer_surprise)}"

    def get_birthday_surprise_campfire_community(self):
        """This function returns information about a surprise event for members of the Lazy Dog Campfire Community who are celebrating their birthday.

        **Instructions**:
        - Trigger this function **only** when the user enters the exact phrase: **"$BIRTHDAY_SURPRISE_CAMPFIRE_COMMUNITY_$"** in the chat.
        - Do **not** call the function under any other circumstances unless the user explicitly states both that they are a member of the Lazy Dog Campfire Community and that they are celebrating their birthday.
        - Ensure the user's membership in the Campfire Community and their birthday celebration are both mentioned or confirmed before calling the function.
        """

        community_surprise = [
            """Birthday Campfire Feast
Description: Members celebrating their birthday receive a complimentary Birthday Campfire Feast for two, which includes signature dishes and desserts served campfire-style at their Lazy Dog home location. The meal is complemented by a cozy campfire-themed setup (outdoor seating, string lights, etc.).
Surprise Element: Members also receive a surprise Lazy Dog branded campfire blanket to take home, perfect for future outdoor adventures.""",
            """ Birthday Adventure Box
Description: For Campfire Community members, a special Birthday Adventure Box is delivered to their home. The box includes birthday-themed camping gear, gourmet marshmallows, a mini birthday cake, and a Lazy Dog recipe card for a DIY birthday campfire treat.
Surprise Element: A surprise birthday message from the Lazy Dog team and a voucher for a free meal on their next dine-in visit.""",
            """ Birthday Bonfire Night
Description: On the member’s birthday, they are invited to a Birthday Bonfire Night at select Lazy Dog locations, where they and their guests can enjoy s’mores, complimentary appetizers, and a private outdoor movie screening. The birthday member gets to pick the movie!
Surprise Element: The birthday member receives a personalized campfire mug with their name and birthdate etched into it.""",
        ]

        # randomly select a surprise event
        return f"The user is celebrating their birthday today! Here's a special surprise event for them: \n\n{random.choice(community_surprise)}"

    def get_birthday_surprise_campfire_club(self):
        """This function returns information about a surprise event for members of the Lazy Dog Campfire Club who are celebrating their birthday.

        **Instructions**:
        - Call this function **only** when the user enters the exact phrase: **"$BIRTHDAY_SURPRISE_CAMPFIRE_CLUB_$"** in the chat.
        - Do **not** trigger the function in any other situation unless the user explicitly confirms both their membership in the Lazy Dog Campfire Club and that they are celebrating their birthday.
        - Ensure that both the user's club membership and birthday celebration are clearly mentioned or verified before calling the function.
        """

        club_surprise = [
            """Exclusive Birthday Chef’s Dinner
Description: Campfire Club members receive an invite to an Exclusive Birthday Chef’s Dinner. This intimate multi-course meal is crafted by Lazy Dog’s executive chef and includes dishes not available on the regular menu. It’s a private dining experience with other birthday celebrants of the month.
Surprise Element: The birthday member is gifted a framed photo from the event with the chef, along with a personalized apron with their name embroidered.""",
            """Birthday Campfire Cocktail Party
Description: Members celebrating their birthday are treated to a Campfire Cocktail Party at their home location, complete with complimentary cocktails, appetizers, and a custom birthday cake served by the restaurant. The cocktail menu is designed around the member’s favorite flavors (which they can indicate when joining).
Surprise Element: The birthday member is surprised with a custom cocktail shaker engraved with their initials and a Lazy Dog cocktail recipe book.""",
            """Birthday Adventure Getaway
Description: For their birthday, one lucky Campfire Club member each month is randomly selected to win a Birthday Adventure Getaway package, which includes an all-expenses-paid weekend at a nearby camping or glamping site for two. The package includes curated Lazy Dog meals and activities such as kayaking or hiking.
Surprise Element: The getaway includes a surprise Lazy Dog Adventure Kit, complete with outdoor essentials (e.g., a picnic set, thermos, hiking gear), personalized for the winner.""",
        ]

        # randomly select a surprise event
        return f"The user is celebrating their birthday today! Here's a special surprise event for them: \n\n{random.choice(club_surprise)}"

    def get_seasonal_special_food(self):
        """This function returns information about a seasonal special promotion. It can be used to promote
        a limited-time offer or recommend food choices to the user in various situations.

        ##Examples:
        1. When the user explicitly asks for promotions, deals, or discounts.
        Example:
        - "Do you have any special deals today?"
        - "Are there any seasonal promotions?"

        2. When the user asks for food or drink recommendations.
        Example:
        - "What do you recommend from your menu?"
        - "I'm not sure what to get, any suggestions?"

        **Function Behavior:**
        - The function will suggest a seasonal or limited-time food promotion based on available offers.
        """
        seasonal_food_events = [
            """Pick Your Own Duo,
Description: 1 handcrafted beverage + 1 choice of our bowls for only $15! The beverage is non-alcoholic.
Availability: Available daliy til 4 pm.
Poster url: https://lazydog-assets.s3.amazonaws.com/uploads/nuggets/668587e68fba27d62d7b44c4/Roadtrip_Duo_Hompage_Bannersdesktop_v2.jpg."""
        ]
        return f"Recommend some random dishes from the menu, and then tell the user about a promotion: \n\n{random.choice(seasonal_food_events)} with the promotion poster image display."

    def get_tv_dinner(self):
        """This function provides information about the TV dinners available for take-out. It can be used
        to inform users about convenient, ready-to-heat meals during specific situations.

        ##Examples
        1. When the user asks for take-out or to-go meal options.
        Example:
        - "Do you have any meals that I can take home?"
        - "What do you have for take-out?"

        2. When the user is checking out or finalizing their order.
        Example:
        - "Would you like to add any take-home options to your order?"
        - "Before you go, would you like to grab a TV dinner for later?"

        3. When the user asks for easy-to-prepare meal recommendations.
        Example:
        - "Do you have any meals that are quick and easy to prepare?"
        - "I'm looking for something I can heat up at home, any suggestions?"

        **Function Behavior:**
        - The function returns a description of the TV dinners as ready-to-heat, in-house frozen meals that come in retro-style trays.
        """

        tv_dinner = [
            """TV Dinners,
Description: Made in-house, frozen in retro-style trays, and ready to pop in the oven when you need them.
Poster url: https://lazydog-assets.s3.amazonaws.com/uploads/nuggets/66d874fa8fba2703cec98af5/TVDinners_Cooler_Bag_Web_Banners_UPDATE_Desktop_1600x600.jpg"""
        ]
        return f"Tell the user about the TV dinners: \n\n{tv_dinner} with the poster image displayed."
