"""A quick and dirty metamodel based on Pydantic."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import rdflib
from pydantic import BaseModel
from rdflib import RDF, Graph, Literal, Namespace, URIRef

__all__ = [
    "PredicateAnnotation",
    "RDFAnnotation",
    "RDFBaseModel",
    "RDFInstanceBaseModel",
    "WithPredicate",
    "WithPredicateNamespace",
]


class RDFAnnotation:
    """A harness that should be used as annotations inside a type hint."""


class PredicateAnnotation(RDFAnnotation, ABC):
    """For serializing values."""

    @abstractmethod
    def add_to_graph(self, graph: Graph, node: URIRef, value: Any) -> None:
        """Add."""
        raise NotImplementedError


class WithPredicate(PredicateAnnotation):
    """Serializes a field representing a value/entity using the given predicate."""

    def __init__(self, predicate: URIRef):
        """Initialize the configuration with a predicate."""
        self.predicate = predicate

    def add_to_graph(self, graph: Graph, node: URIRef, value: Any) -> None:
        """Add to the graph."""
        if isinstance(value, RDFInstanceBaseModel):
            value.add_to_graph(graph)
        elif isinstance(value, Literal):
            graph.add((node, self.predicate, value))
        elif isinstance(value, str | float | int | bool):
            graph.add((node, self.predicate, Literal(value)))
        elif isinstance(value, list):
            for subvalue in value:
                # we're recursively calling since all the elements in
                # the list should get the same predicate treatment
                self.add_to_graph(graph, node, subvalue)
        else:
            raise NotImplementedError(f"unhandled: {value}")


class WithPredicateNamespace(PredicateAnnotation):
    """Serializes a field representing an entity in a given namespace with the given predicate."""

    def __init__(self, predicate: URIRef, namespace: Namespace) -> None:
        """Initialize the annotation with the predicate and namespace."""
        self.namespace = namespace
        self.predicate = predicate

    def add_to_graph(self, graph: Graph, node: URIRef, value: str) -> None:
        """Add to the graph."""
        graph.add((node, self.predicate, self.namespace[value]))


class RDFBaseModel(BaseModel, ABC):
    """A base class for Pydantic models that can be serialized to RDF."""

    def model_dump_turtle(self) -> str:
        """Serialize turtle."""
        return self.get_graph().serialize(format="ttl")

    def get_graph(self) -> rdflib.Graph:
        """Get as RDF."""
        graph = rdflib.Graph()
        self.add_to_graph(graph)
        return graph

    @abstractmethod
    def add_to_graph(self, graph: rdflib.Graph) -> URIRef:
        """Add to the graph."""


class RDFInstanceBaseModel(RDFBaseModel, ABC):
    """A base class for Pydantic models that represent instances.

    - All subclasses must specify their ``rdf_type`` and a function
      for getting the URI for the instance.
    - All fields are opt-in for serialization to RDF and fully explicit.
    """

    #: A variable denoting the RDF type that all instances of this
    #: class will get serialized with
    rdf_type: ClassVar[URIRef]

    @abstractmethod
    def get_uri(self) -> URIRef:
        """Get the URI representing the instance."""
        raise NotImplementedError

    def add_to_graph(self, graph: rdflib.Graph) -> URIRef:
        """Add to the graph."""
        node = self.get_uri()
        graph.add((node, RDF.type, self.rdf_type))
        for name, field in self.__class__.model_fields.items():
            for annotation in field.metadata:
                if isinstance(annotation, PredicateAnnotation):
                    value = getattr(self, name)
                    annotation.add_to_graph(graph, node, value)
        return node
