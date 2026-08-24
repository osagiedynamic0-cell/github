"""Content generation with Gemini."""

from gemini_client import GeminiClient
from config import OFFER_NAME, OFFER_URL, AGENCY_TERM, MARKETING_TERM, RECOMMENDATION_TEXT

gemini = GeminiClient()

CONTROVERSIAL_STATEMENTS = [
    "If you're a freelancer and you're still chasing low-paying clients, you're burning time you could be spending on agencies and businesses that actually have budgets.",
    "Cold outreach is dead for freelancers. Agencies and businesses expect emails, not LinkedIn DMs.",
    "Upwork is a race to the bottom for freelancers. Agencies and businesses pay premium rates. Go direct.",
    "If you're an affiliate and you're still promoting random products, you're wasting time. Agencies and businesses buy tools and software — promote those.",
    "Most affiliates fail because they promote the wrong products. Agencies and businesses spend money on tools, software, and courses.",
    "The real money in affiliate marketing is promoting to agencies and businesses — they actually buy the tools you're promoting."
]

def generate_content(platform: str, audience: str, is_link: bool, question=None) -> str:
    controversy = random.choice(CONTROVERSIAL_STATEMENTS)

    if audience == "freelancer":
        core = f"""{controversy}

I started trying to find clients a few months back. Some replied. Most didn't. What I realized is {AGENCY_TERM} pay better than random clients."""
    else:
        core = f"""{controversy}

I spent 3 hours today looking for products to promote. Found nothing good. What I realized is {AGENCY_TERM} are the perfect buyers because they spend money on tools and software."""

    link_text = f"\n\n{RECOMMENDATION_TEXT}\n{OFFER_URL}" if is_link else "\n\nWhat's your biggest blocker with finding clients?"

    prompt = f"""
Generate a {platform} post for {audience}s.

CRITICAL RULES:
- Start with the controversial statement
- Always say "{OFFER_NAME}" — never "list"
- Always say "{AGENCY_TERM}" — never just "agencies"
- No hype words: game-changer, must-have
- The recommendation must feel natural

CONTROVERSIAL STATEMENT:
{core}

Then add:
Switched to {MARKETING_TERM} instead of cold DMs. Started getting better responses.
Tried building an {OFFER_NAME} from scratch. Took forever.
Decided to buy one instead.
{link_text}

{"Question to answer: " + question if question else ""}
Generate only the content, no extra text.
"""
    return gemini.generate(prompt, platform)
