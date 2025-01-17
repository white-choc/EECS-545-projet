import argparse
import os
import torch
from attrdict import AttrDict
from loader import data_loader
from models import TrajectoryGenerator, displacement_error, final_displacement_error
from functions import relative_to_abs, get_dset_path

parser = argparse.ArgumentParser()
parser.add_argument('--test_model', default="SocialGANModel_500_pred_12", type=str)
parser.add_argument('--num_samples', default=20, type=int)
parser.add_argument('--dset_type', default='test', type=str)

def get_generator(checkpoint):
    args = AttrDict(checkpoint['args'])
    generator = TrajectoryGenerator(
        obs_len=args.obs_len, 
        pred_len=args.pred_len, 
        embedding_dim=args.embedding_dim,
        encoder_h_dim=args.encoder_h_dim_g, 
        decoder_h_dim=args.decoder_h_dim_g,
        mlp_dim=args.mlp_dim, 
        num_layers=args.num_layers, 
        noise_dim=args.noise_dim,
        noise_type=args.noise_type,
        noise_mix_type=args.noise_mix_type,
        bottleneck_dim=args.bottleneck_dim,
        batch_norm=args.batch_norm)
    generator.load_state_dict(checkpoint['g_state'])
    generator.cuda()
    generator.train()
    return generator


def evaluate_helper(error, seq_start_end):
    sum_ = 0
    error = torch.stack(error, dim=1)

    for (start, end) in seq_start_end:
        start = start.item()
        end = end.item()
        _error = error[start:end]
        _error = torch.sum(_error, dim=0)
        _error = torch.min(_error)
        sum_ += _error
    return sum_


def evaluate(args, loader, generator, num_samples):
    ade_outer, fde_outer = [], []
    total_traj = 0
    with torch.no_grad():
        for batch in loader:
            batch = [tensor.cuda() for tensor in batch]
            (obs_traj, pred_traj_gt, obs_traj_rel, pred_traj_gt_rel,
             non_linear_ped, loss_mask, seq_start_end) = batch

            ade, fde = [], []
            total_traj += pred_traj_gt.size(1)

            for _ in range(num_samples):
                pred_traj_fake_rel = generator(
                    obs_traj, obs_traj_rel, seq_start_end
                )
                pred_traj_fake = relative_to_abs(
                    pred_traj_fake_rel, obs_traj[-1]
                )
                ade.append(displacement_error(
                    pred_traj_fake, pred_traj_gt, mode='raw'
                ))
                fde.append(final_displacement_error(
                    pred_traj_fake[-1], pred_traj_gt[-1], mode='raw'
                ))

            ade_sum = evaluate_helper(ade, seq_start_end)
            fde_sum = evaluate_helper(fde, seq_start_end)

            ade_outer.append(ade_sum)
            fde_outer.append(fde_sum)
        ade = sum(ade_outer) / (total_traj * args.pred_len)
        fde = sum(fde_outer) / (total_traj)
        return ade, fde


def main(args):

    path = "./" + args.test_model + ".pt"
    SavedModel = torch.load(path)
    generator = get_generator(SavedModel)
    
    _args = AttrDict(SavedModel['args'])

    test_path = get_dset_path(_args.dataset_name, args.dset_type)
    #print(test_path)
    _, test_loader = data_loader(_args, test_path)
    
    ade, fde = evaluate(_args, test_loader, generator, args.num_samples)
    print('Dataset: {}, Pred Len: {}, ADE: {:.4f}, FDE: {:.4f}'.format(
         _args.dataset_name, _args.pred_len, ade, fde))
    

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
