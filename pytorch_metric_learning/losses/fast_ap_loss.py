import torch
from .base_metric_loss_function import BaseMetricLossFunction
from ..utils import loss_and_miner_utils as lmu

class FastAPLoss(BaseMetricLossFunction):
    def __init__(self, num_bins, **kwargs):
        super().__init__(**kwargs)
        self.num_bins = int(num_bins)
        self.num_edges = self.num_bins + 1

    """
    Adapted from https://github.com/kunhe/FastAP-metric-learning
    """
    def compute_loss(self, embeddings, labels, indices_tuple):
        miner_weights = lmu.convert_to_weights(indices_tuple, labels)
        N = labels.size(0)
        a1_idx, p_idx, a2_idx, n_idx = lmu.get_all_pairs_indices(labels)
        I_pos = torch.zeros(N, N).to(embeddings.device)
        I_neg = torch.zeros(N, N).to(embeddings.device)
        I_pos[a1_idx, p_idx] = 1
        I_neg[a2_idx, n_idx] = 1
        N_pos = torch.sum(I_pos, dim=1)
        dist_mat = lmu.dist_mat(embeddings, squared=True)

        histogram_max = 4. if self.normalize_embeddings else torch.max(dist_mat).item()
        histogram_delta = histogram_max / self.num_bins
        mid_points = torch.linspace(0., histogram_max, steps=self.num_edges)
        pos_hist = torch.zeros(N, self.num_edges).to(embeddings.device)
        neg_hist = torch.zeros(N, self.num_edges).to(embeddings.device)
        for i in range(self.num_edges):
            pulse = torch.nn.functional.relu(1 - torch.abs(dist_mat-mid_points[i])/histogram_delta)
            pos_hist[:,i] = torch.sum(pulse * I_pos, dim=1)
            neg_hist[:,i] = torch.sum(pulse * I_neg, dim=1)

        total_pos_hist = torch.cumsum(pos_hist, dim=1)
        total_hist = torch.cumsum(pos_hist + neg_hist, dim=1)
        
        loss = 0
        h_pos_product = pos_hist * total_pos_hist
        safe_H = (h_pos_product > 0) & (total_hist > 0)
        if torch.sum(safe_H) > 0:
            FastAP = torch.zeros_like(pos_hist).to(embeddings.device)
            FastAP[safe_H] = h_pos_product[safe_H] / total_hist[safe_H]
            FastAP = torch.sum(FastAP, dim=1)
            safe_N = (N_pos > 0)
            if torch.sum(safe_N) > 0:
                FastAP = FastAP[safe_N] / N_pos[safe_N]
                FastAP = FastAP * miner_weights[safe_N]
                loss = 1 - torch.mean(FastAP)
        return loss

