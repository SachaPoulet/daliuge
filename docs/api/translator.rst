Translator API
==============

.. contents::
   :local:

Artefacts and pipeline
----------------------

.. automodule:: dlg.translator.artefacts
   :members:

.. automodule:: dlg.translator.pipeline
   :members:

.. automodule:: dlg.translator.errors
   :members:

Preparation
-----------

.. automodule:: dlg.translator.stages.prepare.params
   :members:

.. autofunction:: dlg.translator.stages.prepare.config.fill_config

Unrolling
---------

.. automodule:: dlg.translator.stages.unroll.stage
   :members:

.. automodule:: dlg.translator.stages.unroll.model
   :members:

.. automodule:: dlg.translator.stages.unroll.coordinate
   :members:

Construct handlers
^^^^^^^^^^^^^^^^^^

.. automodule:: dlg.translator.stages.unroll.constructs.base
   :members:
   :undoc-members:

.. automodule:: dlg.translator.stages.unroll.constructs.registry
   :members:
   :undoc-members:

.. automodule:: dlg.translator.stages.unroll.constructs.leaf
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.scatter
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.gather
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.groupby
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.loop
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.branch
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.mpi
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.service
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.unroll.constructs.subgraph
   :members:
   :undoc-members:
   :show-inheritance:

Partitioning
------------

.. automodule:: dlg.translator.stages.partition.stage
   :members:

.. autofunction:: dlg.translator.stages.partition.stage.known_algorithms

.. automodule:: dlg.translator.stages.partition.scheduler
   :members:

Partition algorithms
^^^^^^^^^^^^^^^^^^^^

.. automodule:: dlg.translator.stages.partition.algorithms.base
   :members:

.. automodule:: dlg.translator.stages.partition.algorithms.registry
   :members:

.. automodule:: dlg.translator.stages.partition.algorithms.none
   :members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.partition.algorithms.metis
   :members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.partition.algorithms.mysarkar
   :members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.partition.algorithms.min_num_parts
   :members:
   :show-inheritance:

.. automodule:: dlg.translator.stages.partition.algorithms.pso
   :members:
   :show-inheritance:

Mapping
-------

.. automodule:: dlg.translator.stages.map.stage
   :members:

Physical Graph Manager
----------------------

.. automodule:: dlg.translator.web.pg_manager
   :members:

Command-line interface
----------------------

.. automodule:: dlg.translator.tool_commands
   :members:
   :undoc-members:
