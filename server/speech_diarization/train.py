"""
code snippets and structure insipration taken from HarryVolek on GitHub
"""
import os
import random
import time
import h5py
import torch
from torch.optim.lr_scheduler import ExponentialLR
from torch.utils.data import DataLoader

from hparam import hparam as hp
from network import SpeechEmbedder
from ge2e_loss import GE2ELoss
from utils import get_centroids, get_cossim 
from loader import AMI_Dataset

def train(model_path):
    # set device to train on (CPU or GPU)
    device = torch.device(hp.device)

    # dataset loader(fetches a batch)
    train_dataset = AMI_Dataset()
    train_loader = DataLoader(train_dataset, shuffle=False, num_workers=hp.train.num_workers, drop_last=True) 

    embedder_net = SpeechEmbedder().to(device)
    
    if hp.train.restore:
        embedder_net.load_state_dict(torch.load(model_path))
    ge2e_loss = GE2ELoss(device)
    
    #Both net and loss have trainable parameters
    optimizer = torch.optim.SGD([
                    {'params': embedder_net.parameters()},
                    {'params': ge2e_loss.parameters()}
                ], lr=hp.train.lr)
    

    #reduce_lr = lambda lr: lr // 50
    lr_schceduler = ExponentialLR(optimizer, gamma=0.1)


    os.makedirs(hp.train.checkpoint_dir, exist_ok=True)
    
    embedder_net.train()
    iteration = 0
    reduce_lr_id = 500

    for e in range(hp.train.epochs):
        total_loss = 0
        for batch_id, batch in enumerate(train_loader): 
            
            print("batch No.", batch_id, end=' ')
            batch = batch.to(device)
            
            embeddings = torch.zeros([batch.shape[1], batch.shape[2] ,hp.model.proj]) #(num_speakers, num_utter,num_features)
            #print("Embeddings shape:", embeddings.shape)

            #for worker in batch:
            #    for speaker_id,speaker in enumerate(worker):
            #        print(f"speaker shape {speaker.shape}")
            #        for utter_id, utterance in enumerate(speaker):
            #            print(f"utter shape: {utterance.shape}")
            #            embeddings[speaker_id,utter_id] = embedder_net(utterance)                

            embeddings = embedder_net(batch[0])
            #gradient accumulates

            optimizer.zero_grad()
            
            #get loss, call backward, step optimizer
            loss = ge2e_loss(embeddings) #wants (Speaker, Utterances, embedding)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(embedder_net.parameters(), 3.0)
            torch.nn.utils.clip_grad_norm_(ge2e_loss.parameters(), 1.0)
            optimizer.step()
            
            print('Curr loss:' , loss)

            if batch_id != 0 and batch_id % reduce_lr_id == 0:
                print('Reduced lr in 0.1')
                lr_schceduler.step()
                reduce_lr_id //= 2

            #total_loss = total_loss + loss

            iteration += 1
            if (batch_id + 1) % hp.train.log_interval == 0:
                mesg = "{0}\tEpoch:{1}[{2}/{3}],Iteration:{4}\tLoss:{5:.4f}\t\n".format(time.ctime(), e+1,
                        batch_id+1, len(train_dataset)//hp.train.N, iteration,loss)
                print(mesg)
                if hp.train.log_file is not None:
                    with open(hp.train.log_file,'a') as f:
                        f.write(mesg)
                    
        if hp.train.checkpoint_dir is not None and (e + 1) % hp.train.checkpoint_interval == 0:
            embedder_net.eval().cpu()
            ckpt_model_filename = "ckpt_epoch_" + str(e+1) + "_batch_id_" + str(batch_id+1) + ".pth"
            ckpt_model_path = os.path.join(hp.train.checkpoint_dir, ckpt_model_filename)
            torch.save(embedder_net.state_dict(), ckpt_model_path)
            embedder_net.to(device).train()

    #save model
    embedder_net.eval().cpu()
    save_model_filename = "final_epoch_" + str(e + 1) + "_batch_id_" + str(batch_id + 1) + ".model"
    save_model_path = os.path.join(hp.train.checkpoint_dir, save_model_filename)
    torch.save(embedder_net.state_dict(), save_model_path)
    
    print("\nDone, trained model saved at", save_model_path)

def test(model_path):
    pass
    # TODO: calc DER
        
if __name__=="__main__":
    if hp.training:
        train(hp.model.model_path)
    else:
        test(hp.model.model_path)