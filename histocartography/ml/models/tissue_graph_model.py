import dgl
from typing import Dict
import torch
import os 

from ..layers.mlp import MLP
from .base_model import BaseModel
from .. import MultiLayerGNN
from ..layers.constants import GNN_NODE_FEAT_IN
from .zoo import MODEL_NAME_TO_URL, MODEL_NAME_TO_CONFIG
from ...utils.io import download_box_link


class TissueGraphModel(BaseModel):
    """
    Tissue Graph Model. Apply a GNN on tissue level.
    """

    def __init__(
        self,
        gnn_params,
        classification_params,
        node_dim,
        **kwargs):
        """
        TissueGraphModel model constructor

        Args:
            gnn_params: (dict) GNN configuration parameters.
            classification_params: (dict) classification configuration parameters.
            node_dim (int): Tissue node feature dimension. 
        """

        super().__init__(**kwargs)

        # 1- set class attributes
        self.node_dim = node_dim  
        self.gnn_params = gnn_params
        self.classification_params = classification_params
        self.readout_op = gnn_params['readout_op']

        # 2- build tissue graph params
        self._build_tissue_graph_params()

        # 3- build classification params
        self._build_classification_params()

        # 4- load pretrained weights if needed
        if self.pretrained:
            model_name = self._get_checkpoint_id()
            if model_name:
                checkpoint_path = os.path.join(
                    os.path.dirname(__file__),
                    '..',
                    '..',
                    '..',
                    'checkpoints'
                )
                download_box_link(
                    url=MODEL_NAME_TO_URL[model_name],
                    out_fname=os.path.join(checkpoint_path, model_name)
                )
                self.load_state_dict(
                    torch.load(os.path.join(checkpoint_path, model_name))
                )
            else:
                raise NotImplementedError('There is not available TG-GNN checkpoint for the provided params.')

    def _get_checkpoint_id(self):

        # 1st level-check: Model type, GNN layer type, num classes
        model_type = 'tggnn'
        layer_type = self.gnn_params['layer_type'].replace('_layer', '')
        num_classes = self.num_classes
        candidate = 'bracs_' + model_type + '_' + str(num_classes) + '_classes_' + layer_type + '.pt'
        print(candidate, list(MODEL_NAME_TO_URL.keys()))
        if candidate not in list(MODEL_NAME_TO_URL.keys()):
            print('Fail 1')
            return ''

        # 2nd level-check: Look at all the specific params      
        cand_config = MODEL_NAME_TO_CONFIG[candidate]

        for cand_key, cand_val in cand_config['gnn_params'].items():
            if hasattr(self.superpx_gnn, cand_key):
                if cand_val != getattr(self.superpx_gnn, cand_key): 
                    print('Fail 2')
                    return ''
            else:
                if cand_val != getattr(self.superpx_gnn.layers[0], cand_key): 
                    print('Fail 2bis')
                    return ''

        for cand_key, cand_val in cand_config['classification_params'].items():
            if cand_val != getattr(self.pred_layer, cand_key):
                print('Fail 3')
                return ''

        if cand_config['node_dim'] != self.node_dim:
            print('Fail 4')
            return ''

        return candidate

    def _build_tissue_graph_params(self):
        """
        Build multi layer GNN for tissue processing.
        """
        self.superpx_gnn = MultiLayerGNN(
            input_dim=self.node_dim,
            **self.gnn_params
        )

    def _build_classification_params(self):
        """
        Build classification parameters
        """
        if self.readout_op == "concat":
            emd_dim = self.gnn_params['output_dim'] * self.gnn_params['num_layers']
        else:
            emd_dim = self.gnn_params['output_dim']

        self.pred_layer = MLP(in_dim=emd_dim,
                              hidden_dim=self.classification_params['hidden_dim'],
                              out_dim=self.num_classes,
                              num_layers=self.classification_params['num_layers']
                              )

    def forward(self, data):
        """
        Foward pass.
        :param superpx_graph: (DGLGraph) superpx graph
        @TODO: input can be:
            - DGLGraph
            - [DGLGraph]
            - [tensor (adj), tensor (node features)]
        """

        if isinstance(data, dgl.DGLGraph) or isinstance(data[0], dgl.DGLGraph):
            # 1. GNN layers over the low level graph
            if isinstance(data, list):
                superpx_graph = data[0]
            else:
                superpx_graph = data
            feats = superpx_graph.ndata[GNN_NODE_FEAT_IN]
            graph_embeddings = self.superpx_gnn(superpx_graph, feats)
        else:
            adj, feats = data[0], data[1]
            graph_embeddings = self.superpx_gnn(adj, feats)

        # 2. Run readout function
        logits = self.pred_layer(graph_embeddings)
        return logits

    def set_lrp(self, with_lrp):
        self.superpx_gnn.set_lrp(with_lrp)
        self.pred_layer.set_lrp(with_lrp)

    def lrp(self, out_relevance_score):
        # lrp over the classification
        relevance_score = self.pred_layer.lrp(out_relevance_score)

        # lrp over the GNN layers
        relevance_score = self.superpx_gnn.lrp(relevance_score)

        return relevance_score
