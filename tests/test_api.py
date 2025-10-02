"""Tests for the metamodel."""

import unittest
from collections.abc import Collection
from typing import Annotated, ClassVar

import rdflib
from pydantic import AnyUrl, Field
from rdflib import DCTERMS, FOAF, RDF, RDFS, SDO, SKOS, XSD, Literal, Namespace, Node, URIRef

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


class BasePerson(RDFInstanceBaseModel):
    """A base class for person."""

    rdf_type: ClassVar[URIRef] = SDO.Person

    orcid: str

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


class TestAPI(unittest.TestCase):
    """Tests for the API."""

    def assert_triples(
        self, triples: Collection[tuple[Node, Node, Node]], graph: rdflib.Graph
    ) -> None:
        """Check the triples are the same."""
        self.assertEqual(
            sorted(set(triples)),
            sorted(graph.triples((None, None, None))),
        )

    def test_simple_predicate(self) -> None:
        """Demonstrate the simple metadata model."""

        class PersonWithName(BasePerson):
            """Represents a person."""

            orcid: str
            name: Annotated[str, WithPredicate(RDFS.label)]

        person = PersonWithName(orcid=CHARLIE_ORCID, name=CHARLIE_NAME)
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ORCID[CHARLIE_ORCID], RDFS.label, Literal(CHARLIE_NAME)),
            },
            person.get_graph(),
        )

    def test_simple_predicate_namespace(self) -> None:
        """Demonstrate the simple metadata model."""

        class PersonWithPredicateNamespace(BasePerson):
            """Represents a person."""

            orcid: str
            wikidata: Annotated[str, WithPredicateNamespace(HAS_WIKIDATA, WIKIDATA)]

        person = PersonWithPredicateNamespace(orcid=CHARLIE_ORCID, wikidata=CHARLIE_WD)
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ORCID[CHARLIE_ORCID], HAS_WIKIDATA, WIKIDATA[CHARLIE_WD]),
            },
            person.get_graph(),
        )

    def test_nested(self) -> None:
        """Test a nested model."""

        class Organization(RDFInstanceBaseModel):
            """Represents an organization."""

            rdf_type: ClassVar[URIRef] = SDO.Organization

            ror: str
            name: Annotated[str, WithPredicate(RDFS.label)]

            def get_node(self) -> URIRef:
                """Get the URI for the organization, based on its ROR."""
                return ROR[self.ror]

        class PersonWithNested(BasePerson):
            """Represents a person."""

            orcid: str
            affiliations: Annotated[list[Organization], WithPredicate(FOAF.member)] = Field(
                default_factory=list
            )

        person = PersonWithNested(
            orcid=CHARLIE_ORCID,
            affiliations=[Organization(ror=NFDI_ROR, name=NFDI_NAME)],
        )
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (ROR[NFDI_ROR], RDF.type, SDO.Organization),
                (ROR[NFDI_ROR], RDFS.label, Literal(NFDI_NAME)),
                (ORCID[CHARLIE_ORCID], FOAF.member, ROR[NFDI_ROR]),
            },
            person.get_graph(),
        )

    def test_triple(self) -> None:
        """Test a triple model."""
        mapping_uri = URIRef("https://example.org/testuri")
        s_uri = URIRef("https://purl.obolibrary.org/obo/CHEBI_10001")
        o_uri = URIRef("http://id.nlm.nih.gov/mesh/C067604")

        class SemanticMapping(RDFTripleBaseModel):
            """Represents a mapping."""

            s: Annotated[Entity, IsSubject()]
            p: Annotated[Entity, IsPredicate()]
            o: Annotated[Entity, IsObject()]
            justification: Annotated[str, WithPredicateNamespace(HAS_JUSTIFICATION, SEMAPV)]
            author: Annotated[str, WithPredicateNamespace(DCTERMS.contributor, ORCID)]

            def get_node(self) -> Node:
                """Get a pre-defined node instead of a blank one, for testing purposes."""
                return mapping_uri

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
                (mapping_uri, RDF.type, RDF.Statement),
                (mapping_uri, RDF.subject, s_uri),
                (mapping_uri, RDF.predicate, SKOS.exactMatch),
                (mapping_uri, RDF.object, o_uri),
                (mapping_uri, HAS_JUSTIFICATION, SEMAPV["ManualMappingCuration"]),
                (mapping_uri, DCTERMS.contributor, ORCID[CHARLIE_ORCID]),
            },
            graph,
        )

    def test_url(self) -> None:
        """Test a model that uses URL annotations."""

        class PersonWithHomepage(BasePerson):
            """A person with a homepage."""

            orcid: str
            homepage: Annotated[AnyUrl, WithPredicate(FOAF.homepage)]

        # FIXME there's a weird bug that AnyURL adds a trailing slash?
        person = PersonWithHomepage(orcid=CHARLIE_ORCID, homepage="https://cthoyt.com/")
        self.assert_triples(
            {
                (ORCID[CHARLIE_ORCID], RDF.type, SDO.Person),
                (
                    ORCID[CHARLIE_ORCID],
                    FOAF.homepage,
                    Literal("https://cthoyt.com/", datatype=XSD.anyURI),
                ),
            },
            person.get_graph(),
        )
