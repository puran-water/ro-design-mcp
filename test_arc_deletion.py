#!/usr/bin/env python3
"""Test arc deletion behavior in Pyomo."""

from pyomo.environ import *
from pyomo.network import *
from idaes.core import FlowsheetBlock
from idaes.models.unit_models import Feed, Product
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock

m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)
m.fs.properties = MCASParameterBlock(solute_list=['Na_+', 'Cl_-'])

# Create units
m.fs.feed = Feed(property_package=m.fs.properties)
m.fs.product = Product(property_package=m.fs.properties)

# Create arc
m.fs.test_arc = Arc(source=m.fs.feed.outlet, destination=m.fs.product.inlet)

# Check arc exists
print(f'Arc exists before deletion: {hasattr(m.fs, "test_arc")}')
print(f'Arc value before deletion: {m.fs.test_arc}')

# Delete arc
m.fs.del_component(m.fs.test_arc)

# Check arc after deletion
print(f'Arc exists after deletion: {hasattr(m.fs, "test_arc")}')
if hasattr(m.fs, 'test_arc'):
    print(f'Arc value after deletion: {m.fs.test_arc}')
    print(f'Arc is None: {m.fs.test_arc is None}')