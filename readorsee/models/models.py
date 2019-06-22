from torchvision import models
import torch.nn as nn
import torch
from allennlp.modules.elmo import Elmo, batch_to_ids
from readorsee import settings
from readorsee.data.models import Config
from readorsee.features.sentence_embeddings import SIF, PMEAN

class ResNet(nn.Module):

    def __init__(self, resnet_size=50, n_classes=2):
        super(ResNet, self).__init__()

        self.resnet = getattr(models, "resnet" + str(resnet_size))
        self.resnet = self.resnet(pretrained=True)

        # Freezing all layers but layer3, layer4 and avgpool
        c = 0
        for child in self.resnet.children():
            c += 1
            if c < 7:
                for param in child.parameters():
                    param.requires_grad = False

        n_ftrs = self.resnet.fc.in_features

        self.resnet.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(n_ftrs, n_classes)
        )

    def forward(self, x):
        x = self.resnet(x)
        return x


class ELMo(nn.Module):

    def __init__(self, fine_tuned):
        """
        fine_tuned = if False uses the ELMo trained on the wikipedia PT-BR dump.
                     Otherwise uses the ELMo trained on the wikipedia tuned 
                     with our 31 million tweets dataset.

        """
        super(ELMo, self).__init__()
        self.fine_tuned = fine_tuned

        self.configuration = Config()

        options_path = (settings.PATH_TO_FT_ELMO_OPTIONS if fine_tuned else
                        settings.PATH_TO_ELMO_OPTIONS)
        weights_path = (settings.PATH_TO_FT_ELMO_WEIGHTS if fine_tuned else
                        settings.PATH_TO_ELMO_WEIGHTS)

        self.embedding = Elmo(options_path, weights_path, 1, dropout=0.5,
                              scalar_mix_parameters=[0, 0, 1])

        n_ftrs = self.embedding.get_output_dim()

        if self.configuration.general["mean"] == "pmean":
            n_ftrs = n_ftrs * 3

        self.fc = nn.Sequential(
            nn.Linear(n_ftrs, n_ftrs//2),
            nn.BatchNorm1d(n_ftrs//2),
            nn.ReLU(),
            nn.Linear(n_ftrs//2, 1)
        )
        # self._init_weight()

    def forward(self, x, sif_weights=None):
        x = self.embedding(x)
        masks = x["mask"].float()
        x = x["elmo_representations"][0]
        # ----------------------------------------------------
        x = self._get_mean(x, masks, sif_weights)
        # ----------------------------------------------------
        x = self.fc(x)
        x = x.squeeze()
        return x

    def _get_mean(self, x, masks, sif_weights):
        
        if self.configuration.general["mean"] == "sif":
            sif = SIF()
            sif_embeddings = sif.SIF_embedding(x, masks, sif_weights)
            return sif_embeddings

        elif self.configuration.general["mean"] == "pmean":
            pmean = PMEAN()
            pmean_embedding = pmean.PMEAN_embedding(x)
            return pmean_embedding

        elif self.configuration.general["mean"] == "avg":
            x = x.sum(dim=1)
            masks = masks.sum(dim=1)
            masks = torch.repeat_interleave(masks, 
                        x.size(-1)).view(-1, x.size(-1))
            x = torch.div(x, masks)
            return x
        else:
            raise NotImplementedError


class FastText(nn.Module):
    def __init__(self, fine_tuned):
        """ 
        fine_tuned   = use the fine_tuned model <<Not implemented yet>>
        """
        super(FastText, self).__init__()

        self.fine_tuned = fine_tuned
        n_ftrs = 300

        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(n_ftrs, n_ftrs//2),
            nn.BatchNorm1d(n_ftrs//2),
            nn.ReLU(),
            nn.Linear(n_ftrs//2, 1)
        )

    def forward(self, x):
        x = self.fc(x).squeeze()
        return x

    def init_weight(self, dataset, days):
        pass

def init_weight_xavier_uniform(m):
    if isinstance(m, nn.Linear):
        torch.nn.init.xavier_uniform_(m.weight)
        if m.bias is not None:
            torch.nn.init.zeros_(m.bias)
