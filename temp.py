
from qiskit import QuantumCircuit
import matplotlib.pyplot as plt

qc = QuantumCircuit(6)
qc.cx(0,2)
qc.h(3)
qc.cx(1,3)
qc.h(4)
qc.cx(2,4)
qc.h(5)
qc.cx(3,5)

fig = qc.draw(output='mpl')
fig.savefig("my_circuit.jpg", dpi=300, bbox_inches='tight')
plt.close(fig)
