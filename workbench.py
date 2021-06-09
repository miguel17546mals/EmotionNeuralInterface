from EmotionNeuralInterface.tools.paths_utils import get_paths_experiment
from EmotionNeuralInterface.subject_data.utils import create_subject_data
from EmotionNeuralInterface.data.tokenizer import Tokenizer
#from EmotionNeuralInterface.data.datagen import DataGen
# Datasets Generators
from EmotionNeuralInterface.data.pretext_task.same_channel_single_channel import SameChannel
from EmotionNeuralInterface.data.pretext_task.same_subject_single_channel import SameSubject
from EmotionNeuralInterface.data.pretext_task.consecutive_single_channel import Consecutive

from EmotionNeuralInterface.data.pretext_task.relative_positioning import RelativePositioning
from EmotionNeuralInterface.data.pretext_task.temporal_shifting import TemporalShifting

from EmotionNeuralInterface.data.dataset import NetworkDataSet
from EmotionNeuralInterface.tools.utils import split_data_by_len
from EmotionNeuralInterface.model.loss import ContrastiveLoss

from EmotionNeuralInterface.model.model import SiameseLinearNetwork
from EmotionNeuralInterface.model.model import SiameseNetwork
from EmotionNeuralInterface.model.stage_net import StageNet


import torch
from torch import cuda
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
import torch.nn as nn
import torch.nn.functional as F
#from sklearn.model_selection import train_test_split
from pandas import DataFrame
import os
from random import shuffle, sample, seed
import yaml

from datetime import datetime

from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix
from sklearn.metrics import accuracy_score
from sklearn.metrics import silhouette_samples
from sklearn.metrics import silhouette_score
from pandas import crosstab
import numpy as np  
### PLOTS
from sklearn.manifold import TSNE
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from umap import UMAP

seed(27)

class Workbench(object):
    def __init__(self, config_file):
        with open(config_file) as f:
            self.data = yaml.load(f, Loader=yaml.FullLoader)
            print(self.data)
        self.device = 'cuda' if cuda.is_available() else 'cpu'
        torch.set_grad_enabled(False)
        self.model_config = {}
        self.load_dataset()
        self.load_tokenizer()
        self.dataset_subjects()
        self.datagen_config()
        self.load_dataset_batch()
    
    def load_dataset(self):
        experiments_paths = get_paths_experiment(self.data["dataset"]["dataset_path"])
        self.experiments, self.subjects = create_subject_data(experiments_paths)
        
    def load_tokenizer(self):
        data = self.data["tokenizer"]
        self.tokenizer = Tokenizer(self.subjects, window_size=data["window_size"], stride=data["stride"])

    def dataset_subjects(self):
        data = self.data["dataset_subjects"]
        self.train_subjets, other_subjets = split_data_by_len(self.subjects.copy_list(), data["train_subjects"])
        self.validation_subjets, self.test_subjets = split_data_by_len(other_subjets,data["test_subjects"])
    
    def datagen_config(self):
        data = self.data["datagen_config"]
        self.target_cod = data["target_codification"]
        self.combinate_subjects = data["combinate_subjects"]
        self.channel_iters = data["channel_iters"]
        if data["use_overfitting"]:
            self.datagen_overfitting()
            return
        self.set_train_datagen()
        self.set_validation_datagen()
        self.set_test_datagen()

    def set_train_datagen(self):
        self.train_data_generator = self.get_dataset_generator(self.train_subjets, key_len_multiple="dataset_train_len")
        self.data_train = self.train_data_generator.get_dataset()
        print("Entrenamiento")
        print(self.train_data_generator.dataset_metadata)
        self.training_set = NetworkDataSet(self.data_train, self.tokenizer)


    def set_validation_datagen(self):
        self.validation_data_generator = self.get_dataset_generator(self.validation_subjets, key_len_multiple="dataset_validation_len")
        self.data_validation = self.validation_data_generator.get_dataset()
        print("Validacion")
        print(self.validation_data_generator.dataset_metadata)
        self.validation_set = NetworkDataSet(self.data_validation, self.tokenizer)

    def set_test_datagen(self):
        self.test_data_generator = self.get_dataset_generator(self.test_subjets, key_len_multiple="dataset_test_len")
        self.data_test = self.test_data_generator.get_dataset()
        print("Test")
        print(self.test_data_generator.dataset_metadata)
        self.testing_set = NetworkDataSet(self.data_test, self.tokenizer)


    def get_dataset_generator(self, subjects, key_len_multiple="dataset_len"):
        multiple_channel_dict = self.data["datagen_config"]["multiple_channel"]
        if self.data["datagen_config"]["dataset"] == "same_channel_single_channel":
            return SameChannel(subjects, self.tokenizer, combinate_subjects=self.combinate_subjects, channels_iter=self.channel_iters, targets_cod=self.target_cod)
        elif self.data["datagen_config"]["dataset"] == "same_subject_single_channel":
            return SameSubject(subjects, self.tokenizer, combinate_subjects=self.combinate_subjects, channels_iter=self.channel_iters, targets_cod=self.target_cod)
        elif self.data["datagen_config"]["dataset"] == "consecutive_single_channel":
            return Consecutive(subjects, self.tokenizer, combinate_subjects=self.combinate_subjects, channels_iter=self.channel_iters, targets_cod=self.target_cod)
        elif self.data["datagen_config"]["dataset"] == "relative_positioning_multiple_channel":
            return RelativePositioning(subjects, self.tokenizer, multiple_channel_len=multiple_channel_dict["multiple_channel_len"],
                                        t_pos_max=multiple_channel_dict["t_pos_max"],dataset_len=multiple_channel_dict[key_len_multiple],
                                        max_num_iter=multiple_channel_dict["max_num_iter"],targets_cod=self.target_cod)
        elif self.data["datagen_config"]["dataset"] == "temporal_shifting_multiple_channel":
            return TemporalShifting(subjects, self.tokenizer, multiple_channel_len=multiple_channel_dict["multiple_channel_len"],
                                        t_pos_max=multiple_channel_dict["t_pos_max"],dataset_len=multiple_channel_dict[key_len_multiple],
                                        max_num_iter=multiple_channel_dict["max_num_iter"],targets_cod=self.target_cod)
        
        raise Warning("No valid Dataset")    


    def datagen_overfitting(self):
        train_data_generator = self.get_dataset(self.train_subjets)
        self.data_train = train_data_generator.get_tiny_custom_channel_dataset_test(self.data["datagen_config"]["train_dataset_len"])
        self.data_test = train_data_generator.get_tiny_custom_channel_dataset_test(self.data["datagen_config"]["train_dataset_len"])
        self.training_set = NetworkDataSet(self.data_train, self.tokenizer)
        self.validation_set = NetworkDataSet(self.data_train, self.tokenizer)
        self.testing_set = NetworkDataSet(self.data_test, self.tokenizer)
        self.print_dataset()

    def print_dataset(self):
        print("Train len: {}".format(len(self.data_train)))
        print("Test len: {}".format(len(self.data_test)))


    def load_dataset_batch(self):
        data = self.data["dataset_batch"]
        self.TRAIN_BATCH_SIZE = data["train_batch_size"]
        self.VALID_BATCH_SIZE = data["validation_batch_size"]
        self.TEST_BATCH_SIZE = data["test_batch_size"]
        self.LEARNING_RATE = data["learning_rate"]

        train_params = {'batch_size': self.TRAIN_BATCH_SIZE,
                            'shuffle': True,
                            'num_workers': 0
                        }

        validation_params = {'batch_size': self.VALID_BATCH_SIZE,
                            'shuffle': True,
                            'num_workers': 0
                        }

        test_params = {'batch_size': self.TEST_BATCH_SIZE,
                            'shuffle': True,
                            'num_workers': 0
                        }
        self.training_loader = DataLoader(self.training_set, **train_params)
        self.validation_loader = DataLoader(self.validation_set, **validation_params)
        self.testing_loader = DataLoader(self.testing_set, **test_params)
     
    def get_model_features(self):
        return "CNN-128-64-32-16"

    def get_model_name(self):
        return "model-{}-{}-margin{}-P{}-loss{}-epoch{}".format(self.get_model_features(), 
            self.data["datagen_config"]["dataset"], self.data["loss"]["margin"], self.target_cod["positive"],
            self.data["loss"]["loss_fuction"], self.data["train"]["epochs"])

    def get_model(self):
        if self.data["train"]["load_model"]:
            return torch.load(self.data["train"]["load_model_name"])
        return self.get_type_model()

    def get_type_model(self):
        
        with open(self.data["model"]["model_config_path"]) as f:
            self.model_config = yaml.load(f, Loader=yaml.FullLoader)
            print(self.model_config)
        if self.data["model"]["type"] == "siamese_stagenet":
            return StageNet(self.model_config)
        elif self.data["model"]["type"] == "siamese_conv":
            return SiameseNetwork()
        elif self.data["model"]["type"] == "siamese_linear":
            return SiameseLinearNetwork((self.data["tokenizer"]["window_size"],128,128,64))
        raise Warning("No type model found")


    def get_optimizer(self, model):
        if self.data["optimizer"] == "adam":
            return torch.optim.Adam(model.parameters(), lr=self.LEARNING_RATE)
        elif self.data["optimizer"] == "sgd":
            return torch.optim.SGD(model.parameters(), lr=self.LEARNING_RATE)
        raise Warning("No optimizer")


    def calculate_distance(self, output1, output2):
        return torch.sqrt((output2 - output1).pow(2).sum(1))

    def calculate_label(self, distances):
        return torch.cuda.IntTensor([self.target_cod["positive"] if tensor.item() < self.margin else self.target_cod["negative"] for tensor in distances])

    def calcuate_metric(self, output1, output2, targets):
        distances = self.calculate_distance(output1, output2)
        o_labels = self.calculate_label(distances)
        n_correct = (o_labels==targets).sum().item()
        return n_correct
    
    def set_folders(self, exp_name):
        if not os.path.exists(self.data["model"]["folder_save"]):
            os.mkdir(self.data["model"]["folder_save"])
        base = self.data["model"]["folder_save"]
        self.base_path = os.path.join(base,exp_name)
        if not os.path.exists(self.base_path ):
            os.mkdir(self.base_path )      
        self.plot_path = os.path.join(base,exp_name,"plots")
        if not os.path.exists(self.plot_path):
            os.mkdir(self.plot_path)
        

    def evaluate_model(self, epoch):
        n = 1
        n_correct = 0
        examples = 0
        for _,data in enumerate(self.validation_loader, 0):
            input1 = data["input1"].to(self.device)
            input2 = data["input2"].to(self.device)
            target = data["output"].to(self.device)
            output1, output2 = self.model(input1, input2)
            loss_contrastive = self.loss_function(output1, output2, target.unsqueeze(1))
            eucledian_distance = self.calculate_distance(output1, output2)
            n_correct += self.calcuate_metric(output1, output2, target)
            examples += target.size(0)
            if n % 10000 == 0:
                break
            n += 1
        print ("Accuracy: ", n_correct/examples)
        self.writer.add_scalar("Accuracy/Validation", n_correct/examples, epoch)
        return

    def model_train(self, epoch):
        n = 1
        n_correct = 0
        examples = 0
        distance = nn.PairwiseDistance()
        for _,data in enumerate(self.training_loader, 0):
            input1 = data["input1"].to(self.device)
            input2 = data["input2"].to(self.device)
            target = torch.squeeze(data["output"],0).to(self.device)
            output1, output2 = self.model(input1, input2)
            print("Targets ",target)
            loss_contrastive = self.loss_function(output1, output2, target)
            self.optimizer.zero_grad()
            loss_contrastive.backward()
            self.optimizer.step()
            print("Epoch {} Current loss {}\n".format(epoch,loss_contrastive.item()))
            self.writer.add_scalar("Loss/train", loss_contrastive.item(), epoch)
            eucledian_distance = distance(output1, output2)
            n_correct += self.calcuate_metric(output1, output2, target)
            examples += target.size(0)
            print(eucledian_distance)
            print(target)
            print("Acc ", (n_correct/examples)*100)
            self.writer.add_scalar("Accuracy/train", (n_correct/examples)*100, epoch)
            n += 1
        return

    def prepare_model(self):
        self.model_name = self.get_model_name()
        self.folder = self.base_path
        self.ext = self.data["model"]["extention"]
        self.full_path = os.path.join(self.folder, self.model_name + self.ext)        
        self.model = self.get_model()
        self.model.to(self.device)
        self.margin = self.data["loss"]["margin"]
        self.loss_function = ContrastiveLoss(self.margin)
        #self.loss_function = nn.MarginRankingLoss(margin=self.margin)
        self.optimizer = self.get_optimizer(self.model)

    def train(self):
        self.prepare_model()
        torch.set_grad_enabled(True)
        self.EPOCHS=self.data["train"]["epochs"]
        self.model.train()
        self.writer = SummaryWriter()
        for epoch in range(self.EPOCHS):
            self.model_train(epoch)
            if self.data["train"]["save_each"] == "epoch":
                torch.save(self.model, "{}/{}-epoch-{}.{}".format(self.folder, self.model_name, epoch, self.ext))
                print("Model Saved Successfully")
            if self.data["validation"]["use_each"] == "epoch":
                self.evaluate_model(epoch)
        torch.save(self.model, self.full_path)


    def test(self):
        y_real = []
        y_predict = []
        y_distance = []
        n_correct = 0
        examples = 0
        df = list()
        datalen = len(self.training_set)
        i = 1
        for _,data in enumerate(self.testing_loader, 0):
            input1 = data["input1"].to(self.device)
            input2 = data["input2"].to(self.device)
            targets = torch.squeeze(data["output"],0).to(self.device)
            output1, output2 = self.model(input1, input2)
            loss_contrastive = self.loss_function(output1, output2, targets)
            eucledian_distance = F.pairwise_distance(output1, output2)
            y_real += [target.item() for target in targets.unsqueeze(0)]
            labels_predict = self.calculate_label(self.calculate_distance(output1, output2))
            y_predict += [label.item() for label in labels_predict]
            n_correct += self.calcuate_metric(output1, output2, targets)
            examples += targets.unsqueeze(0).size(0)
            print("Acc= ", n_correct/examples)
            if self.data["model"]["type"] in ["siamese_conv", "siamese_linear"]:
                df.append({'Vector': output1.to("cpu").detach().numpy()[0], "Categ": data["output"].item(), "subject": data["subject1"].item(), "chn": data["chn1"].item(), "estimulo": data["estimulo"].item()})
                df.append({'Vector': output2.to("cpu").detach().numpy()[0], "Categ": data["output"].item(), "subject": data["subject2"].item(), "chn": data["chn2"].item(), "estimulo": data["estimulo"].item()})
            else:
                df.append({'Vector': output1.to("cpu").detach().numpy()[0], "Categ": data["output"].item(), "subject": data["subjects"][0].item(), "chn": len(data["channels"]), "channels": [chn.item() for chn in data["channels"]], "estimulo": data["stimulus"][0].item()})
                df.append({'Vector': output2.to("cpu").detach().numpy()[0], "Categ": data["output"].item(), "subject": data["subjects"][0].item(), "chn": len(data["channels"]), "channels": [chn.item() for chn in data["channels"]], "estimulo": data["stimulus"][0].item()})
            print("Completado: ", i)
            i += 1
        return y_real, y_predict, y_distance, DataFrame.from_dict(df)

    def gen_model_reports(self, y_real, y_predict, y_distance, df):
        Y_P = np.array(y_predict)
        Y_V = np.array(y_real)
        confusion_matrix = crosstab(Y_P, Y_V, rownames=['Real'], colnames=['Predicción'])
        class_report = classification_report(Y_V, Y_P)
        folder = self.plot_path
        report = open(os.path.join(folder,"report.txt"),"w")
        report.write(class_report)
        report.close()
        # TSNE
        #df_plot = df.sample(frac=0.75)
        df_plot = df 
        self.plot_tsne(df_plot)
        #UMAP
        self.plot_umap_proc(df_plot)
        self.save_test_data(df)
        self.get_silhouette_result(df)
        return
    

    def get_silhouette_result(self, df):
        folder = self.plot_path
        report = open(os.path.join(folder,"silhouette.txt"),"w")
        score_category = silhouette_score(np.array(df.Vector.tolist()), np.array(df.Categ.tolist()))
        score_subject = silhouette_score(np.array(df.Vector.tolist()), np.array(df.subject.tolist()))
        if self.data["model"]["type"] in ["siamese_conv", "siamese_linear"]:
            score_channel = silhouette_score(np.array(df.Vector.tolist()), np.array(df.chn.tolist()))
        else:
            score_channel = -999999999
        score_stimulus = silhouette_score(np.array(df.Vector.tolist()), np.array(df.estimulo.tolist()))
        report_txt = """
        Silhouette 
        Score Category: {}
        Score Subject:  {}
        Score Channel:  {}
        Score Stimulus: {}
        """.format(score_category,score_subject,score_channel,score_stimulus)
        report.write(report_txt)
        report.close()   
        return

    def save_test_data(self,df):
        path = os.path.join(self.base_path, 'data_test.csv') 
        return df.to_csv(path)

    def plot_umap_proc(self, df):
        folder = self.plot_path
        umap_2d = UMAP(n_components=2, init='random', random_state=0)
        umap_3d = UMAP(n_components=3, init='random', random_state=0)
        proj_2d = umap_2d.fit_transform(np.array(df.Vector.tolist()))
        proj_3d = umap_3d.fit_transform(np.array(df.Vector.tolist()))
        self.plot_umap(folder,proj_2d,proj_3d,df.Categ,"Categ","category-umap")
        self.plot_umap(folder,proj_2d,proj_3d,df.subject,"subject","subject-umap")
        self.plot_umap(folder,proj_2d,proj_3d,df.chn,"chn","channel-umap")
        self.plot_umap(folder,proj_2d,proj_3d,df.estimulo,"estimulo","estimulo-umap")

    def plot_umap(self, folder, proj_2d, proj_3d, data, label, basename):
        fig_2d = px.scatter(proj_2d, x=0, y=1, color=data, labels={'color': label}).write_image(self.get_plot_name(folder,basename,"2d"))
        fig_3d = px.scatter_3d(proj_3d, x=0, y=1, z=2,color=data, labels={'color': label}).write_image(self.get_plot_name(folder,basename,"3d"))
        return 

    def plot_tsne(self, df):
        folder = self.plot_path
        m = TSNE(n_components=3,learning_rate=50)
        tsne_features = m.fit_transform(np.array(df.Vector.tolist()))
        df["x"] = tsne_features[:,0]
        df["y"] = tsne_features[:,1]
        df["z"] = tsne_features[:,2]
        self.plot(folder, df, "Categ", df.Categ, "category-tsne")
        self.plot(folder, df, "subject", df.subject, "subject-tsne")
        self.plot(folder, df, "chn", df.chn, "channel-tsne")
        self.plot(folder, df, "estimulo", df.estimulo, "estimulo-tsne")

    def get_plot_name(self, folder, base, extra):
        return os.path.join(folder,"{}{}.png".format(base,extra))

    def plot(self, folder, df, hue_data, data, basename):
        sns.scatterplot(x="x",y="y", hue=hue_data, data=df).figure.savefig(self.get_plot_name(folder,basename,""))
        px.scatter_3d(df, x='x', y='y', z='z', color=data).write_image(self.get_plot_name(folder,basename,"3d"))
        px.scatter(df, x='x', y='y',color=data).write_image(self.get_plot_name(folder,basename,"2d"))

    def plot_channels(self, folder, df):
        sns.scatterplot(x="x",y="y", hue="chn", data=df).savefig(os.path.join(folder,"channel.png"))
        fig3 = px.scatter_3d(df, x='x', y='y', z='z',color=df.chn)
        fig3_2d = px.scatter(df, x='x', y='y',color=df.chn)
        fig3_2d.write_image(os.path.join(folder,"channel2d.png"))
        fig3.write_image(os.path.join(folder,"channel3d.png"))

    def plot_subject(self, folder, df):
        sns.scatterplot(x="x",y="y", hue="subject", data=df).savefig(os.path.join(folder,"subject.png"))
        fig2 = px.scatter_3d(df, x='x', y='y', z='z',color=df.subject)
        fig2_2d = px.scatter(df, x='x', y='y',color=df.subject)
        fig2_2d.write_image(os.path.join(folder,"subject2d.png"))
        fig2.write_image(os.path.join(folder,"subject3d.png"))

    def plot_category(self, folder, df):
        sns.scatterplot(x="x",y="y", hue="Categ", data=df).savefig(os.path.join(folder,"category.png"))
        fig = px.scatter_3d(df, x='x', y='y', z='z',color=df.Categ)
        fig_2d = px.scatter(df, x='x', y='y', color=df.Categ)
        fig_2d.write_image(os.path.join(folder,"category2d.png"))
        fig.write_image(os.path.join(folder,"category3d.png"))

    def save_yaml_conf(self):
        path = os.path.join(self.base_path, 'data.yaml') 
        with open(path, 'w') as outfile:
            yaml.dump(self.data, outfile, default_flow_style=False)
        path_model = os.path.join(self.base_path, 'model_config.yaml') 
        # Se lee otra vez el archivo de configuracion por un bug
        with open(self.data["model"]["model_config_path"]) as f:
            self.model_config = yaml.load(f, Loader=yaml.FullLoader)
        #######################################
        with open(path_model, 'w') as outfile:
            yaml.dump(self.model_config , outfile, default_flow_style=False)        
        

    def run(self):
        #import pdb;pdb.set_trace()
        branch = "emotion_neural_interface_{}_dev-{}_{}".format(self.get_model_name(),self.data["github"]["dev"], datetime.now().timestamp())
        self.data["branch"] = branch
        self.set_folders(branch)
        command = "git checkout -b {}".format(branch)
        os.system(command)
        self.train()
        self.model.eval()
        y_real, y_predict, y_distance, df =self.test()
        self.gen_model_reports(y_real, y_predict, y_distance, df)
        self.save_yaml_conf()
        os.system("git add .")
        os.system("git commit -m 'Se agrega el experimento'")
        os.system("git checkout main")

    def run_test(self):
        branch = "emotion_neural_interface_{}_dev-{}_{}".format(self.get_model_name(),self.data["github"]["dev"], datetime.now().timestamp())
        self.data["branch"] = branch
        self.set_folders(branch)
        command = "git checkout -b {}".format(branch)
        os.system(command)
        self.prepare_model()
        self.model.eval()
        y_real, y_predict, y_distance, df =self.test()
        self.gen_model_reports(y_real, y_predict, y_distance, df)
        self.save_yaml_conf()
        os.system("git add .")
        os.system('git commit -m "Se agrega el experimento"')
        os.system("git checkout main")    
        return
    
exp = Workbench("config/config.yaml")
exp.run()