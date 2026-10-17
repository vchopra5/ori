OriSim3D by Rémi Koutchérawy

Source: https://github.com/RemiKoutcherawy/OriSim3D
Commit: 50bc4257f76e0513115c648cb4c1fc4a0d6b396c

MIT license in LICENSE. Examples are copied unchanged.

Local patches in js/Model.js: bisector3d uses the supporting infinite lines and
compares closest-point distance with a scale-relative tolerance instead of exact
floating-point equality. Subdivided or slightly rounded edge segments can otherwise
be misclassified as disjoint, producing the wrong crease or no crease.
