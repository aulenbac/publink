"""Extract info from eXtract Dark Data (xDD) (https://geodeepdive.org/)."""

# Import packages
import requests
import bs4
import re
from publink import publink


class SearchXdd():
    """Class allowing for searching of xDD publication database."""

    def __init__(self, search_terms="10.5066", route="snippets"):
        """Initialize search pubs object.

        Parameters
        ----------
        search_terms: str, default is USGS DOI prefix "10.5066"
            comma separated search terms, no spaces e.g. "10.5066,10.4344"
        route: str, default "snippets"
            available routes described at https://geodeepdive.org/api

        Notes
        ----------
        Search terms not available for all routes in xDD

        """
        self.xdd_api_base = "https://geodeepdive.org/api"
        self.search_terms = search_terms.split(",")
        self.route = route
        self.response_data = []
        self.search_urls = []
        self.next_url = ""
        self.response_hits = 0
        self.response_status = "error"
        self.response_message = "No request made."

    def all_search_terms(self):
        """Create list of search terms each with space at each position.

        In processing of articles occasionally words are split due to page
        breaks. This gives us a list of possible search terms to query to
        help us address this issue. Only use for snippet route.

        Results
        ----------
        self.search_terms: list
            list of strings having each search term and iterations of the
            search terms with a space added at each index position not
            including position 0 or x, where x is the length of the string.
            Example:
                initial search term = ["fun"]
                search terms = ["fun", "f un", "fu n"]

        """
        for term in self.search_terms:
            len_term = len(term)
            new_terms = []
            for i in range(1, len_term):
                new_term = f"{term[:i]} {term[i:]}"
                new_terms.append(new_term)
        self.search_terms.extend(new_terms)

    def build_query_urls(self, params="full_results&clean"):
        """Build xDD query urls to search user defined terms.

        Results
        ----------
        self.search_urls: list of strings
            List of urls to query.

        """
        for search_term in self.search_terms:
            api_route = f"{self.xdd_api_base}/{self.route}"
            q = f"?term={search_term}&{params}"
            url = f"{api_route}{q}"
            self.search_urls.append(url)

    def get_data(self):
        """Get data from xDD for all search terms."""
        for url in self.search_urls:
            self.next_url = url
            self.query_xdd()

    def query_xdd(self):
        """Query xDD for results for specific query."""
        while self.next_url != "":
            r = requests.get(self.next_url)
            if r.status_code == 200 and "success" in r.json():
                json_response = r.json()
                response_hits = json_response["success"]["hits"]
                page_data = json_response["success"]["data"]
                self.response_data.extend(page_data)
                self.next_url = json_response["success"]["next_page"]
                self.response_status = "success"
                self.response_message = "Successful response."
            else:
                self.next_url = ""
                if r.status_code == 200 and "success" not in r.json():
                    self.response_status = "no data"
                    self.response_message = f"Request returned no data. \
                        Verify request is valid."
                elif r.status_code != 200:
                    self.response_status = "error"
                    self.response_message = f"Request returned status code: \
                        {r.status_code}."
                    break
                else:
                    self.response_status = "error"
                    self.response_message = f"Unknown error."
                    break

        if self.response_status == "success":
            self.response_hits += response_hits


class GetDoiMentions():
    """Class extracting DOI mentions from xDD snippets."""

    def __init__(self, xdd_response, search_terms=["10.5066"]):
        """Initialize search pubs object.

        Parameters
        ----------
        search_terms: list of str, default is USGS DOI prefix ["10.5066"]
            terms to search across xDD corpus
        route: str, default "snippets"
            available routes described at https://geodeepdive.org/api

        Notes
        ----------
        Search terms not available for all routes in xDD

        """
        self.search_terms = [i.upper() for i in search_terms]
        self.response_data = xdd_response

    def get_specific_doi(self):
        """Pair publication with exact match of full DOI.

        Use when full DOIs used as search terms.

        Notes
        ----------
        This will not return occasions where DOI is split by
        a space unless that space is specified in search term.

        """
        self.related_dois = []
        for ref in self.response_data:
            if "doi" in ref.keys() and ref["doi"] != "":
                pub_doi = publink.doi_formatting(ref["doi"])
                for hl in ref["highlight"]:
                    pairs = [{"pub_doi": pub_doi,
                              "data_doi": i
                              } for i in self.search_terms if i in hl
                             ]
                    self.related_dois.extend(pairs)

        # Remove duplicate pairs
        self.related_dois = [
                dict(t) for t in {tuple(d.items()) for d in self.related_dois}
                ]

    def get_usgs_doi_mentions(self):
        """Pair publication with match of full DOI.

        Accounts for splits in DOI, doesn't require exact match.
        Relies on formating that is specific to all USGS data DOIs.

        """
        self.related_dois = []
        prefix = "10.5066"
        for ref in self.response_data:
            if "doi" in ref.keys() and ref["doi"] != "":
                pub_doi = publink.doi_formatting(ref["doi"])
                for hl in ref["highlight"]:
                    hl = clean_highlight(hl, self.search_terms, prefix)
                    # string to list for index of words
                    hl_words = hl.split(' ')
                    # get words from snippet with search prefix
                    have_prefix = list(set([
                        hl_word for hl_word in hl_words
                        if prefix in hl_word
                    ]))

                    for mention in have_prefix:
                        doi, doi_certainty = extract_usgs_doi(
                            hl_words, mention
                            )
                        if doi is not None:
                            pair = {"pub_doi": pub_doi, "data_doi": doi}
                            self.related_dois.append(pair)

        # Remove duplicate pairs
        self.related_dois = [
                dict(t) for t in {tuple(d.items()) for d in self.related_dois}
                ]


def clean_highlight(highlight_txt, search_terms, usgs_prefix='10.5066'):
    """Clean xDD highlight text.

    Parameters
    ----------
    highlight_txt: str
        string that includes a search term
    search_terms: list of str
        terms being searched
    usgs_prefix: str, default '10.5066'

    Returns
    ----------
    hl_clean: str

    """
    highlight_txt = highlight_txt.upper()
    hl_nohtml = bs4.BeautifulSoup(
        highlight_txt, features="html.parser").get_text()
    hl_clean = clean_unicode(hl_nohtml)

    included_terms = [
        i.upper() for i in search_terms
        if i in hl_clean
    ]
    for term in included_terms:
        hl_clean = hl_clean.replace(term, usgs_prefix)

    return hl_clean


def extract_usgs_doi(hl_words, mention, usgs_prefix='10.5066'):
    """Extract DOI string from xDD highlight.

    Parameters
    ----------
    hl_words: list of str
        highlight in list of string format
    mention: str
        word in hl_word that contains usgs prefix
    usgs_prefix: str, default = '10.5066'

    Returns
    ----------
    doi: str
        16 character str starting with "10.5066"
    doi_certainty: str
        options include "most certain", "certain", "less certain"

    """
    doi = None
    doi_certainty = None

    test = f"{usgs_prefix}{mention.split(usgs_prefix)[1]}"
    if len(test) == 16:
        doi = test
        doi_certainty = "most certain"
    elif len(test) == 17 and test.endswith("."):
        doi = test[:16]
        doi_certainty = "most certain"
    elif len(test) > 16:
        doi = test[:16]
        doi_certainty = "less certain"
    else:
        i = hl_words.index(mention)
        while (len(hl_words) > i+1) and doi is None:
            test = f"{test}{hl_words[i+1]}"
            if len(test) == 16:
                doi_certainty = "most certain"
                doi = test
            elif len(test) == 17 and test.endswith("."):
                doi_certainty = "most certain"
                doi = test[:16]
            elif len(test) > 16:
                doi_certainty = "less certain"
                doi = test[:16]
            i += 1
    if doi is not None and not doi.startswith('10.5066/'):
        doi = None

    return doi, doi_certainty


def clean_unicode(full_txt):
    """Deal with some escaped unicode issues.

    Notes
    ----------
    Short term solution, reported to xDD
    """
    full_txt = re.sub(
        r"\u200b|\u2009|\u200a|\xa0",
        "",
        full_txt,
    )
    return full_txt