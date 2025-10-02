"""Tests for the metamodel."""

import unittest
from collections.abc import Collection
from typing import Annotated, ClassVar

import rdflib
from pydantic import Field
from rdflib import FOAF, RDF, RDFS, SDO, Literal, Namespace, Node, URIRef

from pydantic_metamodel.api import RDFInstanceBaseModel, WithPredicate, WithPredicateNamespace

EX = Namespace("https://example.org/")
ORCID = Namespace("https://orcid.org/")
ROR = Namespace("https://ror.org/")
WIKIDATA = Namespace("https://www.wikidata.org/wiki/")
HAS_WIKIDATA = EX["hasWikidata"]


class Organization(RDFInstanceBaseModel):
    """Represents an organization."""

    rdf_type: ClassVar[URIRef] = SDO.Organization

    ror: str
    name: Annotated[str, WithPredicate(RDFS.label)]

    def get_uri(self) -> URIRef:
        """Get the URI for the organization, based on its ROR."""
        return ROR[self.ror]


class Person(RDFInstanceBaseModel):
    """Represents a person."""

    rdf_type: ClassVar[URIRef] = SDO.Person

    orcid: str
    name: Annotated[str, WithPredicate(RDFS.label)]
    wikidata: Annotated[str, WithPredicateNamespace(HAS_WIKIDATA, WIKIDATA)]
    affiliations: Annotated[list[Organization], WithPredicate(FOAF.member)] = Field(
        default_factory=list
    )

    def get_uri(self) -> URIRef:
        """Get the URI for the person, based on their ORCiD."""
        return ORCID[self.orcid]


CHARLIE_ORCID = "0000-0003-4423-4370"
CHARLIE_NAME = "Charles Tapley Hoyt"
CHARLIE_WD = "Q47475003"
NFDI_ROR = "05qj6w324"
NFDI_NAME = "NFDI"


class TestAPI(unittest.TestCase):
    """Tests for the API."""

    def test_simple(self) -> None:
        """Demonstrate the simple metadata model."""
        person = Person(orcid=CHARLIE_ORCID, wikidata=CHARLIE_WD, name=CHARLIE_NAME)
        graph = person.get_graph()
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ORCID[CHARLIE_ORCID], RDFS.label, Literal(CHARLIE_NAME)),
                (ORCID[CHARLIE_ORCID], HAS_WIKIDATA, WIKIDATA[CHARLIE_WD]),
            },
            graph,
        )

    def test_nested(self) -> None:
        """Test a nested model."""
        person = Person(
            orcid=CHARLIE_ORCID,
            wikidata=CHARLIE_WD,
            name=CHARLIE_NAME,
            affiliations=[Organization(ror=NFDI_ROR, name=NFDI_NAME)],
        )
        graph = person.get_graph()
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ORCID[CHARLIE_ORCID], RDFS.label, Literal(CHARLIE_NAME)),
                (ORCID[CHARLIE_ORCID], HAS_WIKIDATA, WIKIDATA[CHARLIE_WD]),
                (ROR[NFDI_ROR], RDF.type, SDO.Organization),
                (ROR[NFDI_ROR], RDFS.label, Literal(NFDI_NAME)),
                (ORCID[CHARLIE_ORCID], FOAF.member, ROR[NFDI_ROR]),
            },
            graph,
        )

    def assert_triples(
        self, triples: Collection[tuple[Node, Node, Node]], graph: rdflib.Graph
    ) -> None:
        """Check the triples are the same."""
        self.assertEqual(
            sorted(set(triples)),
            sorted(graph.triples((None, None, None))),
        )
