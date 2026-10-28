"""Annotated per-core congested-layer percentages, with a fixed 0–100% scale."""
import argparse
import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from heavy_routing import ALGORITHMS, WORKLOADS, ro

NAMES={'qft':'QFT','draper_qft_adder':'Draper QFT adder','qaoa':'QAOA'}

def panel(ax, values, title):
    im=ax.imshow(values.reshape(4,4),cmap='YlOrRd',vmin=0,vmax=100)
    for core,value in enumerate(values):
        row,col=divmod(core,4)
        ax.text(col,row,f'C{core}\n{value:.1f}%',ha='center',va='center',fontsize=9,
                color='white' if value>=55 else '#171717')
    ax.set_xticks(range(4));ax.set_yticks(range(4))
    ax.set_xticks(np.arange(-.5,4,1),minor=True);ax.set_yticks(np.arange(-.5,4,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1.2);ax.tick_params(which='minor',length=0)
    ax.set_xlabel('Mesh column');ax.set_ylabel('Mesh row');ax.set_title(title)
    return im

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    rows=[];values={};denominators={}
    for workload in WORKLOADS:
        for algorithm in ALGORITHMS:
            folder=a.study/'traces'/workload/'seed_42'/algorithm
            core=np.load(folder/'core_demand.npy')
            active=core.sum(axis=1)>0;denominator=int(active.sum())
            assert denominator>0
            if workload in denominators:assert denominator==denominators[workload]
            denominators[workload]=denominator
            trace=ro.read_trace(folder/'requests.txt',4,4)
            hop=np.zeros_like(core)
            for h in trace.hops:hop[h.layer,h.source]+=1;hop[h.layer,h.target]+=1
            assert np.array_equal(active,hop.sum(axis=1)>0)
            for metric,demand in [('route',core),('hop_incidence',hop)]:
                counts=(demand[active]>4).sum(axis=0)
                percentages=100*counts/denominator
                values[workload,algorithm,metric]=percentages
                for c in range(16):
                    rows.append(dict(workload=workload,algorithm=algorithm,metric=metric,core=c,
                                     congested_layers=int(counts[c]),communication_active_layers=denominator,
                                     total_circuit_layers=trace.layers,congested_percent=float(percentages[c])))
    for metric in ('route','hop_incidence'):
        definition='Routes touching core > 4' if metric=='route' else 'Hop-endpoint demand > 4 (relay counts twice)'
        for workload in WORKLOADS:
            fig,axes=plt.subplots(2,4,figsize=(15,8),layout='constrained')
            for ax,algorithm in zip(axes.flat,ALGORITHMS):
                im=panel(ax,values[workload,algorithm,metric],algorithm)
            axes.flat[-1].axis('off')
            axes.flat[-1].text(.05,.6,'Cell = congested layers at this core\n÷ ALL network communication-active layers\n× 100\n\n0% means no overload, not no traffic.',
                              transform=axes.flat[-1].transAxes,fontsize=10,va='center')
            fig.suptitle(f'{NAMES[workload]}: congested layers per core\n96 qubits · four communication slots/core',fontsize=16)
            fig.supxlabel(f'{definition} · denominator = {denominators[workload]} communication-active layers · common 0–100% scale',fontsize=10)
            fig.colorbar(im,ax=axes.ravel().tolist(),label='Congested / communication-active layers (%)',shrink=.8)
            for ext in ('png','pdf'):fig.savefig(a.output/f'congested_layers_{metric}_{workload}.{ext}',dpi=180)
            plt.close(fig)
    with (a.output/'congested_layers.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('Communication-active layer counts:',denominators)
    print('Saved six PNG/PDF figures and exact numerator/denominator CSV to',a.output)

if __name__=='__main__':main()
