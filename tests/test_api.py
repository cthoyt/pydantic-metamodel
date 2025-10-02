"""Tests for the metamodel."""

import unittest
from collections.abc import Collection
from typing import Annotated, ClassVar

import rdflib
from pydantic import AnyUrl, Field
from rdflib import DCTERMS, FOAF, RDF, RDFS, SDO, SKOS, Literal, Namespace, Node, URIRef

from pydantic_metamodel.api import (
    IsObject,
    IsPredicate,
    IsSubject,
    RDFInstanceBaseModel,
    RDFTripleBaseModel,
    RDFUntypedInstanceBaseModel,
    WithPredicate,
    WithPredicateNamespace,
)

EX = Namespace("https://example.org/")
ORCID = Namespace("https://orcid.org/")
ROR = Namespace("https://ror.org/")
SSSOM = Namespace("https://w3id.org/sssom/")
SEMAPV = Namespace("https://w3id.org/semapv/vocab/")
WIKIDATA = Namespace("https://www.wikidata.org/wiki/")
HAS_WIKIDATA = EX["hasWikidata"]
HAS_JUSTIFICATION = SSSOM["mapping_justification"]


class Organization(RDFInstanceBaseModel):
    """Represents an organization."""

    rdf_type: ClassVar[URIRef] = SDO.Organization

    ror: str
    name: Annotated[str, WithPredicate(RDFS.label)]

    def get_node(self) -> URIRef:
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

    def get_node(self) -> URIRef:
        """Get the URI for the person, based on their ORCiD."""
        return ORCID[self.orcid]


CHARLIE_ORCID = "0000-0003-4423-4370"
CHARLIE_NAME = "Charles Tapley Hoyt"
CHARLIE_WD = "Q47475003"
NFDI_ROR = "05qj6w324"
NFDI_NAME = "NFDI"


class Entity(RDFUntypedInstanceBaseModel):
    """A simple entity."""

    uri: str
    name: Annotated[str | None, WithPredicate(RDFS.label)] = None

    def get_node(self) -> Node:
        """Get the node in a simple way."""
        return URIRef(self.uri)


TEST_URI = URIRef("https://example.org/testuri")


class SemanticMapping(RDFTripleBaseModel):
    """Represents a person."""

    s: Annotated[Entity, IsSubject()]
    p: Annotated[Entity, IsPredicate()]
    o: Annotated[Entity, IsObject()]
    justification: Annotated[str, WithPredicateNamespace(HAS_JUSTIFICATION, SEMAPV)]
    author: Annotated[str, WithPredicateNamespace(DCTERMS.contributor, ORCID)]

    def get_node(self) -> Node:
        """Get a pre-defined node instead of a blank one, for testing purposes."""
        return TEST_URI


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

    def test_uri(self) -> None:
        """Test using URIs directly."""

        class Model1(RDFInstanceBaseModel):
            """Represents a person."""

            rdf_type: ClassVar[URIRef] = SDO.Person

            orcid: str
            attribute: Annotated[AnyUrl, WithPredicate(RDFS.seeAlso)]

            def get_node(self) -> URIRef:
                """Get the URI for the person, based on their ORCiD."""
                return ORCID[self.orcid]

        value = "https://example.org/1"
        person = Model1(orcid=CHARLIE_ORCID, attribute=value)
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ORCID[CHARLIE_ORCID], RDFS.seeAlso, URIRef(value)),
            },
            person.get_graph(),
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

    def test_triple(self) -> None:
        """Test a triple model."""
        s_uri = URIRef("https://purl.obolibrary.org/obo/CHEBI_10001")
        o_uri = URIRef("http://id.nlm.nih.gov/mesh/C067604")
        person = SemanticMapping(
            s=Entity(uri=str(s_uri), name="Visnadin"),
            p=Entity(uri=SKOS.exactMatch),
            o=Entity(uri=str(o_uri), name="visnadin"),
            justification="ManualMappingCuration",
            author=CHARLIE_ORCID,
        )
        graph = person.get_graph()
        self.assert_triples(
            {
                (s_uri, RDFS.label, Literal("Visnadin")),
                (o_uri, RDFS.label, Literal("visnadin")),
                (s_uri, SKOS.exactMatch, o_uri),
                (TEST_URI, RDF.type, RDF.Statement),
                (TEST_URI, RDF.subject, s_uri),
                (TEST_URI, RDF.predicate, SKOS.exactMatch),
                (TEST_URI, RDF.object, o_uri),
                (TEST_URI, HAS_JUSTIFICATION, SEMAPV["ManualMappingCuration"]),
                (TEST_URI, DCTERMS.contributor, ORCID[CHARLIE_ORCID]),
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
