import graphlib
import os.path
from warnings import warn

import lark
from pathlib import Path

from compiler.transformers.RemoveTokens import RemoveTokens
from layers.Layer import Layer
from layers.LayerImplWrapper import LayerImplWrapper
from compiler.transformers.CollectLayers import CollectLayers
from compiler.transformers.CheckCF import CheckCF
from compiler.Interpreters import SimpleInterpreter

class LayeredCompiler:
    def __init__(self
                 , implementations_file
                 , layer_base_dir):

        self.implementations_file = Path(implementations_file)
        self.layer_base_dir = Path(layer_base_dir)

        if not self.implementations_file.is_file():
            raise FileNotFoundError(f"Could not find implementations file at {self.implementations_file}")

        if not self.layer_base_dir.is_dir():
            raise FileNotFoundError(f"Could not find layer base directory at {self.layer_base_dir}")

        # Build path for grammar file
        grammar_file = os.path.dirname(os.path.realpath(__file__)) + "/grammar_file.lark"
        self.parser = lark.Lark.open(grammar_file
                                     , parser= "lalr"
                                     , debug=True
                                     , propagate_positions=True
                                     , transformer=RemoveTokens(["newline"]))
        self.layers = dict()

    def typecheck(self, input_file):
        tree = self.parse(input_file)

        self.__typecheck(tree)

        return True

    def __typecheck(self, tree):
        lv = CollectLayers()
        cf_check = CheckCF()

        tree = lv.transform(tree)
        cf_check.visit(tree)

        layer_graph = {}
        self.layers = {}
        for layer_id in lv.layers:
            self.layers[layer_id] = LayerImplWrapper(self.layer_base_dir, lv.layers[layer_id])
            layer_graph[layer_id] = self.layers[layer_id].depends_on()


        # Check for cycles
        try:
            topo_order = graphlib.TopologicalSorter(layer_graph).static_order()
        except graphlib.CycleError as e:
            raise RuntimeError(f"Cycle in layer dependencies: {e.args[0]}")

        # Incrementally typecheck each layer based on their topological order
        for layer_id in topo_order:
            # Dynamically load layer if not already loaded
            if not layer_id in self.layers:
                warn(f"Layer {layer_id} was not loaded during CollectLayers, but is required by at least one other layer. Loading it now.")
                self.layers[layer_id] = LayerImplWrapper(self.layer_base_dir, Layer(layer_id))

            tree = self.layers[layer_id].typecheck(tree)

        return tree

    def parse(self, input_file):
        with open(input_file) as f:
            tree = self.parser.parse(f.read())

        Remover = RemoveTokens(["newline"])
        tree = Remover.transform(tree)
        return tree

    def compile(self, program):
        tree = self.parse(program)

        if not self.__typecheck(tree):
            raise RuntimeError("Typechecking failed")

        return tree
    def run(self, program):
        tree = self.compile(program)

        interpreter = SimpleInterpreter(self.implementations_file)

        return interpreter.run(tree)



