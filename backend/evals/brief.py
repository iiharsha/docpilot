"""The brief's ten questions as a retrieval eval: `uv run python -m evals.brief`.

Each question is run through `retrieve` exactly as written in
`docs/client-brief.md`, fanned out over the filings it concerns. For each
filing it names the evidence an analyst would need, copied from that filing: a
figure where the answer is a number (the current year's, since each 10-K also
prints the years before), a sentence where it is a disclosure. Every string was
drafted from the corpus and is checked against it on each run.

A question that names several topics is also searched once per topic, as an
analyst would type it into a search box: that is how M4's agent is to use
`search_filings`. Searched only as a whole, such a question embeds as an
average of its topics and ranks each one's passages below those touching
several; see architecture.md, "Retrieval Evaluation".

Run it after any change to chunking or retrieval; `harness.py` says how it
scores. `tests/evals/test_brief.py` holds each question to its `minimum`.
"""

import argparse
import asyncio

from app.retrieval.retriever import K, Slice
from evals.harness import Question, evaluate, report

QUESTIONS = (
    Question(
        1,
        "Across Apple's 2021–2025 10-Ks, how did the revenue mix between iPhone, "
        "Services, Mac, iPad, and Wearables change, and which category appears to "
        "have contributed most to any mix shift?",
        # Net sales by category, in MD&A and in Note 2: iPhone, then Services.
        {
            Slice("AAPL", 2021): ("191,973", "68,425"),
            Slice("AAPL", 2022): ("205,489", "78,129"),
            Slice("AAPL", 2023): ("200,583", "85,200"),
            Slice("AAPL", 2024): ("201,183", "96,169"),
            Slice("AAPL", 2025): ("209,586", "109,158"),
        },
    ),
    Question(
        2,
        "For Amazon, compare AWS operating income and margin against North America "
        "and International from 2021–2025. In which years did AWS appear to fund "
        "losses or weaker profitability elsewhere?",
        # Segment net sales (for margin), then segment operating income, each as
        # North America, International, AWS.
        {
            Slice("AMZN", 2021): (
                "279,833",
                "127,787",
                "62,202",
                "7,271",
                "(924)",
                "18,532",
            ),
            Slice("AMZN", 2022): (
                "315,880",
                "118,007",
                "80,096",
                "(2,847)",
                "(7,746)",
                "22,841",
            ),
            Slice("AMZN", 2023): (
                "352,828",
                "131,200",
                "90,757",
                "14,877",
                "(2,656)",
                "24,631",
            ),
            Slice("AMZN", 2024): (
                "387,497",
                "142,906",
                "107,556",
                "24,967",
                "3,792",
                "39,834",
            ),
            Slice("AMZN", 2025): (
                "426,305",
                "161,894",
                "128,725",
                "29,619",
                "4,750",
                "45,606",
            ),
        },
    ),
    Question(
        3,
        "How did NVIDIA describe demand drivers, customer concentration, and supply "
        "constraints for its Data Center business from fiscal 2021 through fiscal "
        "2025?",
        # Data Center revenue in MD&A; customers over 10% of revenue; supply.
        {
            Slice("NVDA", 2021): (
                "Data Center revenue was up 124% from a year ago",
                "No customer represented 10% or more of total revenue for fiscal years 2021",
                "We may also face supply constraints caused by natural disasters or other events",
            ),
            Slice("NVDA", 2022): (
                "Data Center revenue was up 58% from a year ago",
                "No customer represented 10% or more of total revenue for fiscal years 2022",
                "limited supply or capacity in our supply chain, as we are in today",
            ),
            Slice("NVDA", 2023): (
                "Data Center revenue was up 41% from a year ago",
                "No customer represented 10% or more of total revenue for fiscal years 2023",
                "In periods of shortages impacting the semiconductor industry and/or limited supply or capacity in our supply chain, the lead times on our orders may be extended",
            ),
            Slice("NVDA", 2024): (
                "Data Center revenue for fiscal year 2024 was up 217%",
                "Sales to one customer, Customer A, represented 13% of total revenue",
                "supply constraints or availability issues with respect to any one component have had and may have a broader revenue impact",
            ),
            Slice("NVDA", 2025): (
                "Data Center revenue for fiscal year 2025 was up 142% from a year ago",
                "Sales to direct Customers A, B and C represented 12%, 11% and 11% of total revenue",
                "supply constraints or availability issues with respect to any one component have had and may have a broader revenue impact",
            ),
        },
        topics=(
            "NVIDIA Data Center demand drivers",
            "NVIDIA customer concentration",
            "NVIDIA Data Center supply constraints",
        ),
        # Missed at k=10: FY2021's and FY2023's "No customer represented 10%".
        # A sentence saying there is no concentration ranks below passages that
        # describe customers: in the customer-concentration search, FY2023's is
        # 5th by distance but 22nd by keyword, past the 20 candidates, so
        # passages both searches rank outscore it.
        minimum=13 / 15,
    ),
    Question(
        4,
        "Across Microsoft's 2021–2025 filings, what changed in the way the company "
        "describes Azure, AI infrastructure, and cloud capacity constraints?",
        # Azure's growth in MD&A; how Item 1 describes Azure and its AI
        # infrastructure; capacity — a supplier risk until FY2022, AI demand after.
        {
            Slice("MSFT", 2021): (
                "Azure revenue grew 50%",
                "Azure is a trusted cloud with comprehensive compliance coverage and AI-based security built in.",
                "supplier capacity constraint",
            ),
            Slice("MSFT", 2022): (
                "Azure and other cloud services revenue grew 45%",
                "Azure is a trusted cloud with comprehensive compliance coverage and AI-based security built in.",
                "supplier capacity constraint",
            ),
            Slice("MSFT", 2023): (
                "Azure and other cloud services revenue grew 29%",
                "exclusive cloud provider, Azure powers all of OpenAI",
                "particularly given the growing demand for AI services",
            ),
            Slice("MSFT", 2024): (
                "Azure and other cloud services revenue grew 30%",
                "purpose-built cloud infrastructure for AI workloads",
                "particularly given the growing demand for AI services",
            ),
            Slice("MSFT", 2025): (
                "Azure and other cloud services revenue grew 34%",
                "We offer supercomputing power for AI at scale",
                "particularly given the growing demand for AI services",
            ),
        },
        topics=(
            "Microsoft Azure",
            "Microsoft AI infrastructure",
            "Microsoft cloud capacity constraints",
        ),
    ),
    Question(
        5,
        "For Alphabet, how did Google Search, YouTube ads, Google Network, "
        "subscriptions/platforms/devices, and Google Cloud revenue trends differ "
        "across the available 10-Ks?",
        # Revenues by type, in MD&A and Note 2: Search & other, then Google Cloud.
        {
            Slice("GOOGL", 2021): ("148,951", "19,206"),
            Slice("GOOGL", 2022): ("162,450", "26,280"),
            Slice("GOOGL", 2023): ("175,033", "33,088"),
            Slice("GOOGL", 2024): ("198,084", "43,229"),
            Slice("GOOGL", 2025): ("224,532", "58,705"),
        },
    ),
    Question(
        6,
        "Which of the five companies added, removed, or materially changed "
        "risk-factor language related to AI, cloud infrastructure, export controls, "
        "supply chain concentration, or regulation between 2021 and 2025?",
        # Item 1A, where each company's language on these topics changed.
        {
            # Where manufacturing is concentrated; the EU Digital Markets Act,
            # then AI features, then export controls.
            Slice("AAPL", 2021): (
                "manufacturing is performed in whole or in part by outsourcing partners located primarily in Asia",
                "Digital Markets Act, could, if enacted, require further changes",
            ),
            Slice("AAPL", 2022): (
                "located primarily in Asia, including China mainland, India, Japan, South Korea, Taiwan and Vietnam",
                "Digital Markets Act, could require further changes",
            ),
            Slice("AAPL", 2023): (
                "outsourcing partners located primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam",
                "Digital Markets Act, which the Company is required to comply with by March 2024",
            ),
            Slice("AAPL", 2024): (
                "outsourcing partners located primarily in China mainland, India, Japan, South Korea, Taiwan and Vietnam",
                "such as artificial intelligence features, can increase these and other safety risks",
            ),
            Slice("AAPL", 2025): (
                "in addition to sourcing from partners and facilities located in the U.S.",
                "Laws and regulations, including immigration, labor and employment laws and export controls",
            ),
            # AI as a regulated technology; from FY2023, GPU suppliers.
            Slice("AMZN", 2021): (
                "advertising, artificial intelligence technologies and services",
            ),
            Slice("AMZN", 2022): (
                "advertising, artificial intelligence technologies and services",
            ),
            Slice("AMZN", 2023): (
                "we rely on a limited group of suppliers for semiconductor products, including products related to artificial intelligence infrastructure such as graphics processing units",
            ),
            Slice("AMZN", 2024): (
                "we rely on a limited group of suppliers for semiconductor products, including products related to artificial intelligence infrastructure such as graphics processing units",
            ),
            Slice("AMZN", 2025): (
                "we rely on a limited group of suppliers for semiconductor products, including products related to artificial intelligence infrastructure such as graphics processing units",
            ),
            # AI as one challenge among many; its own risk factor from FY2023,
            # the EU AI Act, then AI's demands on energy and chips.
            Slice("GOOGL", 2021): (
                "including those that use AI and machine learning, raise ethical, technological, legal, regulatory, and other challenges",
            ),
            Slice("GOOGL", 2022): (
                "including those that use AI, require significant investment and raise ethical, technological, legal, regulatory, and other challenges",
            ),
            Slice("GOOGL", 2023): (
                "Issues in the development and use of AI may result in reputational harm and increased liability exposure.",
                "provisional political agreement on a proposed EU AI Act",
            ),
            Slice("GOOGL", 2024): (
                "the EU AI Act came into force on August 1, 2024",
                "industry supply capacity for AI accelerators, including Graphics Processing Units",
            ),
            Slice("GOOGL", 2025): (
                "energy supply is constrained globally due to the significant increase in demand for and limited availability of energy to power AI compute",
                "particularly for specialized AI chips, is limited to a small number of qualified suppliers",
            ),
            # The AI risk factor's heading, reworded four times; AI regulation.
            Slice("MSFT", 2021): (
                "Issues in the use of AI in our offerings may result in reputational harm or liability.",
                "Legislative and regulatory action is emerging in the areas of AI and content moderation",
            ),
            Slice("MSFT", 2022): (
                "Issues in the development and use of AI may result in reputational harm or liability.",
                "new proposed legislation regulating AI in jurisdictions such as the European Union",
            ),
            Slice("MSFT", 2023): (
                "Issues in the development and use of AI may result in reputational or competitive harm or liability.",
                "an AI Act is being considered",
            ),
            Slice("MSFT", 2024): (
                "Issues in the development and use of AI may result in reputational or competitive harm or liability.",
                "AI Act may increase costs or impact the provision or operation of our AI models and services in the European market",
            ),
            Slice("MSFT", 2025): (
                "Issues in the development, deployment, and use of AI may result in reputational or competitive harm or liability.",
                "We are incurring significant costs to build and maintain infrastructure to support cloud-based and AI services, reducing operating margins.",
            ),
            # Export controls, from a general reform to GPUs and China.
            Slice("NVDA", 2021): (
                "regulations to implement the Export Control Reform Act of 2018 could have an adverse effect on our business plans",
            ),
            Slice("NVDA", 2022): (
                "Deemed export control limitations could negatively impact the ability of our research and development teams",
            ),
            Slice("NVDA", 2023): (
                "Export controls targeting GPUs and semiconductors associated with AI, which are increasingly likely",
            ),
            Slice("NVDA", 2024): (
                "semiconductors associated with AI, including GPUs and associated products, are increasingly the focus of export control restrictions",
                "China represented a mid-single digit percentage of our Data Center revenue in the fourth quarter of fiscal year 2024 due to USG licensing requirements",
            ),
            Slice("NVDA", 2025): (
                "semiconductors associated with AI, including GPUs and related products, are increasingly the focus of export control restrictions",
                "The market in China, where our offerings are limited by export controls, is highly competitive",
            ),
        },
        topics=(
            "risk factors related to AI",
            "risk factors related to cloud infrastructure",
            "risk factors related to export controls",
            "risk factors related to supply chain concentration",
            "risk factors related to regulation",
        ),
        # Missed at k=10: Apple's FY2022 Digital Markets Act sentence and its
        # FY2025 export controls, which sit in a risk factor about hiring.
        minimum=38 / 40,
    ),
    Question(
        7,
        "For Apple and NVIDIA, what do the filings say about supplier concentration "
        "or dependence on third-party manufacturing, and did the wording become "
        "more or less urgent over time?",
        # Apple drops "a significant concentration … small number of outsourcing
        # partners" in FY2025; NVIDIA adds "geographic concentration" in FY2023
        # and "concentrated in the Asia-Pacific region" in FY2024.
        {
            Slice("AAPL", 2021): (
                "A significant concentration of this manufacturing is currently performed by a small number of outsourcing partners, often in single locations.",
                "The Company relies on single-source outsourcing partners in the U.S., Asia and Europe",
            ),
            Slice("AAPL", 2022): (
                "a significant concentration of this manufacturing is currently performed by a small number of outsourcing partners",
                "The Company relies on single-source outsourcing partners in the U.S., Asia and Europe",
            ),
            Slice("AAPL", 2023): (
                "a significant concentration of this manufacturing is currently performed by a small number of outsourcing partners",
                "The Company relies on single-source outsourcing partners in the U.S., Asia and Europe",
            ),
            Slice("AAPL", 2024): (
                "a significant concentration of this manufacturing is currently performed by a small number of outsourcing partners",
                "The Company relies on single-source outsourcing partners in the U.S., Asia and Europe",
            ),
            Slice("AAPL", 2025): (
                "The Company relies on single-source partners in the U.S., Asia and Europe",
                "in addition to sourcing from partners and facilities located in the U.S.",
            ),
            Slice("NVDA", 2021): (
                "We do not manufacture the silicon wafers used for our products and do not own or operate a wafer fabrication facility.",
                "we are dependent on industry-leading foundries, such as Taiwan Semiconductor Manufacturing Company Limited",
            ),
            Slice("NVDA", 2022): (
                "We do not manufacture the semiconductors used for our products and do not own or operate a wafer fabrication facility.",
                "limited number of global suppliers, foundries, contract manufacturers, assembly and test providers, and memory manufacturers",
            ),
            Slice("NVDA", 2023): (
                "We use third parties to manufacture and assemble our products, and we have had and may in the future have long manufacturing lead times.",
                "limited number and geographic concentration of global suppliers, foundries, contract manufacturers",
            ),
            Slice("NVDA", 2024): (
                "Our supply chain is concentrated in the Asia-Pacific region.",
                "We use third parties to manufacture and assemble our products, and we have long manufacturing lead times.",
            ),
            Slice("NVDA", 2025): (
                "Our supply chain is mainly concentrated in the Asia-Pacific region.",
                "limited number and geographic concentration of global suppliers, foundries, contract manufacturers",
            ),
        },
    ),
    Question(
        8,
        "Compare capital expenditures and purchase commitments for Microsoft, "
        "Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and "
        "timing of AI/cloud infrastructure investment?",
        # The year's capital expenditures in the cash flow statement (NVIDIA's in
        # Item 15), then total purchase commitments or obligations.
        {
            Slice("MSFT", 2021): ("(20,622)", "31,553"),
            Slice("MSFT", 2022): ("(23,886)", "45,654"),
            Slice("MSFT", 2023): ("(28,107)", "67,818"),
            Slice("MSFT", 2024): ("(44,477)", "72,022"),
            Slice("MSFT", 2025): ("(64,551)", "109,953"),
            Slice("GOOGL", 2021): ("(24,640)", "$13.7 billion"),
            Slice("GOOGL", 2022): ("(31,485)", "$32.0 billion"),
            Slice("GOOGL", 2023): ("(32,251)", "$45.9 billion"),
            Slice("GOOGL", 2024): ("(52,535)", "$55.4 billion"),
            Slice("GOOGL", 2025): ("(91,447)", "$149.1 billion"),
            Slice("AMZN", 2021): ("(61,053)", "34,902"),
            Slice("AMZN", 2022): ("(63,645)", "34,776"),
            Slice("AMZN", 2023): ("(52,729)", "35,484"),
            Slice("AMZN", 2024): ("(82,999)", "50,375"),
            Slice("AMZN", 2025): ("(131,819)", "84,772"),
            Slice("NVDA", 2021): ("(1,128)", "$2.54 billion"),
            Slice("NVDA", 2022): ("(976)", "$9.00 billion"),
            Slice("NVDA", 2023): ("(1,833)", "$4.92 billion"),
            Slice("NVDA", 2024): ("(1,069)", "$16.1 billion"),
            Slice("NVDA", 2025): ("(3,236)", "$30.8 billion"),
        },
        # The line item, in the statement that carries it: "capital
        # expenditures" alone finds the accounting policy for property and
        # equipment. Only Alphabet and Amazon restate the figure in MD&A.
        topics=(
            "cash flow statement: purchases of property and equipment",
            "purchase commitments",
        ),
    ),
    Question(
        9,
        "For each company, summarize the most important geographic revenue "
        "exposures disclosed in the latest 10-K, then identify any year-over-year "
        "changes that could matter to an analyst.",
        # The latest 10-K's revenue by geography, which also prints the prior
        # years: its largest regions for FY2025.
        {
            # Americas, Europe, Greater China.
            Slice("AAPL", 2025): ("178,353", "111,032", "64,377"),
            # United States, Germany, United Kingdom.
            Slice("AMZN", 2025): ("489,657", "45,900", "43,212"),
            # United States, EMEA, APAC.
            Slice("GOOGL", 2025): ("194,229", "117,152", "67,680"),
            # United States, other countries.
            Slice("MSFT", 2025): ("144,546", "137,178"),
            # United States, Singapore, Taiwan, China (including Hong Kong).
            Slice("NVDA", 2025): ("61,257", "23,684", "20,573", "17,108"),
        },
    ),
    Question(
        10,
        "If an analyst asks whether the filings prove that generative AI improved "
        "margins for any of these companies, what evidence exists in the corpus, "
        "and where should the bot refuse to infer beyond the filings?",
        # What each filing gives as the reasons its margins moved, from the years
        # generative AI appears. None claims AI improved them; Amazon says such
        # effects are difficult to isolate. Retrieval has to surface the reasons
        # given, so the model can say what the filings do and do not support.
        {
            Slice("AAPL", 2023): (
                "Products gross margin percentage increased during 2023 compared to 2022 due to cost savings and a different Products mix",
            ),
            Slice("AAPL", 2024): (
                "Products gross margin and Products gross margin percentage increased during 2024 compared to 2023 due to cost savings",
            ),
            Slice("AAPL", 2025): (
                "Products gross margin percentage decreased during 2025 compared to 2024 primarily due to a different mix of products and tariff costs",
            ),
            Slice("AMZN", 2023): (
                "have direct and indirect impacts on our results of operations that are difficult to isolate and quantify",
            ),
            Slice("AMZN", 2024): (
                "including artificial intelligence, have direct and indirect impacts on our results of operations that are difficult to isolate and quantify",
            ),
            Slice("AMZN", 2025): (
                "including artificial intelligence, have direct and indirect impacts on our results of operations that are difficult to predict, isolate, and quantify",
                "including to support our artificial intelligence and machine learning initiatives",
            ),
            Slice("GOOGL", 2023): (
                "such as AI in Search, that could affect our monetization trends",
            ),
            Slice("GOOGL", 2024): (
                "such as AI in Search, that could affect our monetization trends",
            ),
            Slice("GOOGL", 2025): (
                "which could affect revenue growth rates and margin trends",
                "developing and serving AI offerings require more compute power than our historical consumer and enterprise offerings",
            ),
            Slice("MSFT", 2023): (
                "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins.",
            ),
            Slice("MSFT", 2024): (
                "inclusive of scaling our AI infrastructure",
                "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins.",
            ),
            Slice("MSFT", 2025): (
                "Microsoft Cloud gross margin percentage decreased to 69% driven by the impact of scaling our AI infrastructure",
                "reducing operating margins",
            ),
            Slice("NVDA", 2023): (
                "Gross margin for fiscal year 2023 declined from a year ago, driven by $2.17 billion of inventory charges",
            ),
            Slice("NVDA", 2024): (
                "Gross margin increased in fiscal year 2024, primarily driven by Data Center revenue growth",
                "while they have driven increased demand for Data Center, the long-term trajectory is unknown",
            ),
            Slice("NVDA", 2025): (
                "Gross margin increased in fiscal year 2025 driven by a higher mix of Data Center revenue.",
            ),
        },
        topics=("generative AI and margins", "what drove changes in margins"),
        # Missed at k=10: NVIDIA's FY2023 margin decline from inventory charges.
        minimum=19 / 20,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.brief", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--k", type=int, default=K, help=f"passages per filing (default {K})"
    )
    parser.add_argument(
        "--question",
        type=int,
        action="append",
        help="only this question; repeat for more",
    )
    args = parser.parse_args(argv)
    questions = [q for q in QUESTIONS if not args.question or q.number in args.question]

    scores = asyncio.run(evaluate(questions, args.k))
    print(report(scores, args.k))
    failed = any(not s.passed or s.not_in_filing for s in scores)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
