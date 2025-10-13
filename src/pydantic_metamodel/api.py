"""A quick and dirty metamodel based on Pydantic."""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeAlias, Union

import rdflib
from pydantic import AnyUrl, BaseModel
from pydantic_core import core_schema
from pydantic_core.core_schema import AfterValidatorFunctionSchema
from rdflib import RDF, XSD, BNode, Graph, Literal, Namespace, Node, URIRef
from typing_extensions import TypeVar

__all__ = [
    "IsPredicateObject",
    "PredicateAnnotation",
    "PredicateObject",
    "RDFAnnotation",
    "RDFBaseModel",
    "RDFInstanceBaseModel",
    "RDFResource",
    "WithPredicate",
    "WithPredicateNamespace",
    "Year",
]


class Year(int):
    """Wrapper around a year."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> AfterValidatorFunctionSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.int_schema(),  # Input must be an integer
            serialization=core_schema.to_string_ser_schema(),  # Serialize via str()
        )


Primitive: TypeAlias = str | float | int | bool | datetime.date | datetime.datetime | Year

AddableBase: TypeAlias = Union[Node, Primitive, "RDFInstanceBaseModel", AnyUrl]

#: A type hint for things that can be handled
Addable: TypeAlias = AddableBase | list["Addable"]


class RDFResource(URIRef):
    """Wrapper type for RDFlib URIRef that works with Pydantic."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> AfterValidatorFunctionSchema:
        return core_schema.no_info_after_validator_function(
            URIRef,
            core_schema.str_schema(),  # Input must be a string
            serialization=core_schema.to_string_ser_schema(),  # Serialize via str()
        )


T = TypeVar("T")


class PredicateObject(BaseModel, Generic[T]):
    """A predicate-object pair."""

    predicate: RDFResource
    object: T


class RDFAnnotation:
    """A harness that should be used as annotations inside a type hint."""


class PredicateAnnotation(RDFAnnotation, ABC):
    """For serializing values."""

    @abstractmethod
    def add_to_graph(self, graph: Graph, node: Node, value: Addable) -> None:
        """Add."""
        raise NotImplementedError

    def _handle_object(self, graph: Graph, value: AddableBase) -> Node:
        if isinstance(value, RDFInstanceBaseModel):
            return value.add_to_graph(graph)
        elif isinstance(value, Node):
            return value
        elif isinstance(value, AnyUrl):
            return Literal(value.unicode_string(), datatype=XSD.anyURI)
        elif isinstance(value, Year):
            return Literal(str(value), datatype=XSD.gYear)
        elif isinstance(value, Primitive):
            return Literal(value)
        else:
            raise TypeError(f"unhandled type: {value}")


class IsPredicateObject(PredicateAnnotation):
    """A flag for objects that are predicate-object pairs."""

    def add_to_graph(self, graph: Graph, node: Node, value: Addable) -> None:
        """Add."""
        if isinstance(value, list):
            for subvalue in value:
                self.add_to_graph(graph, node, subvalue)
        elif isinstance(value, PredicateObject):
            graph.add((node, value.predicate, self._handle_object(graph, value.object)))
            # TODO support for other fields that would become
            #  axioms on this triple?
        else:
            raise TypeError


class WithPredicate(PredicateAnnotation):
    """Serializes a field representing a value/entity using the given predicate."""

    def __init__(self, predicate: URIRef):
        """Initialize the configuration with a predicate."""
        self.predicate = predicate

    def add_to_graph(self, graph: Graph, node: Node, value: Addable) -> None:
        """Add to the graph."""
        if isinstance(value, list):
            for subvalue in value:
                # we're recursively calling since all the elements in
                # the list should get the same predicate treatment
                self.add_to_graph(graph, node, subvalue)
        else:
            graph.add((node, self.predicate, self._handle_object(graph, value)))


class WithPredicateNamespace(PredicateAnnotation):
    """Serializes a field representing an entity in a given namespace with the given predicate."""

    def __init__(self, predicate: URIRef, namespace: Namespace) -> None:
        """Initialize the annotation with the predicate and namespace."""
        self.namespace = namespace
        self.predicate = predicate

    def add_to_graph(self, graph: Graph, node: Node, value: Addable) -> None:
        """Add to the graph."""
        if isinstance(value, str):
            graph.add((node, self.predicate, self.namespace[value]))
        elif isinstance(value, list):
            for subvalue in value:
                self.add_to_graph(graph, node, subvalue)
        else:
            raise TypeError(
                f"constructing a URI for namespace {self.namespace} requires a string. Got: {value}"
            )


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
    def add_to_graph(self, graph: rdflib.Graph) -> Node:
        """Add to the graph."""

    @abstractmethod
    def get_node(self) -> Node:
        """Get the URI representing the instance."""
        raise NotImplementedError


def _add_annotated(t: BaseModel, graph: rdflib.Graph, node: Node) -> None:
    for name, field in t.__class__.model_fields.items():
        for annotation in field.metadata:
            if isinstance(annotation, PredicateAnnotation):
                if value := getattr(t, name):
                    annotation.add_to_graph(graph, node, value)


class RDFUntypedInstanceBaseModel(RDFBaseModel, ABC):
    """A base class for Pydantic models that represent instances.

    - All subclasses must specify their ``rdf_type`` and a function
      for getting the URI for the instance.
    - All fields are opt-in for serialization to RDF and fully explicit.
    """

    def add_to_graph(self, graph: rdflib.Graph) -> Node:
        """Add to the graph."""
        node = self.get_node()
        _add_annotated(self, graph, node)
        return node


class RDFInstanceBaseModel(RDFUntypedInstanceBaseModel, ABC):
    """A base class for Pydantic models that represent instances.

    - All subclasses must specify their ``rdf_type`` and a function
      for getting the URI for the instance.
    - All fields are opt-in for serialization to RDF and fully explicit.
    """

    #: A variable denoting the RDF type that all instances of this
    #: class will get serialized with
    rdf_type: ClassVar[URIRef]

    def add_to_graph(self, graph: rdflib.Graph) -> Node:
        """Add to the graph."""
        node = super().add_to_graph(graph)
        graph.add((node, RDF.type, self.rdf_type))
        return node


class TripleAnnotation(RDFAnnotation):
    """A base class for triple annotations."""


class IsSubject(TripleAnnotation):
    """An annotation for a field that denotes the subject."""


class IsPredicate(TripleAnnotation):
    """An annotation that denotes the predicate."""


class IsObject(TripleAnnotation):
    """An annotation for a field that denotes the object."""


class RDFTripleBaseModel(RDFBaseModel):
    """A base class for Pydantic models that represent triples and their annotations."""

    def add_to_graph(self, graph: rdflib.Graph) -> Node:
        """Add to the graph."""
        subject = self._get(IsSubject, graph)
        predicate = self._get(IsPredicate, graph)
        obj = self._get(IsObject, graph)
        graph.add((subject, predicate, obj))

        node = self.get_node()
        graph.add((node, RDF.type, RDF.Statement))
        graph.add((node, RDF.subject, subject))
        graph.add((node, RDF.predicate, predicate))
        graph.add((node, RDF.object, obj))
        _add_annotated(self, graph, node)
        return node

    def get_node(self) -> Node:
        """Return a blank node, representing the reified triple."""
        return BNode()

    def _get(self, checker: type[TripleAnnotation], graph: rdflib.Graph) -> Node:
        for name, field in self.__class__.model_fields.items():
            for annotation in field.metadata:
                if isinstance(annotation, checker):
                    value = getattr(self, name)
                    # this has its own stripped-down implementation because
                    # it doesn't allow literals
                    if isinstance(value, RDFBaseModel):
                        return value.add_to_graph(graph)
                    elif isinstance(value, Node):
                        # TODO this can be further refined since subject can't accept literals,
                        #  so have validation be in the checker class itself
                        return value
                    else:
                        raise TypeError(
                            f"{checker} must be with a RDFlib resource or pydantic-metamodel class"
                        )
        raise KeyError
