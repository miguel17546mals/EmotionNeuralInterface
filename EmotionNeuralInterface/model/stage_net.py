import torch.nn as nn
from .encoder import CNN2D
from torch import transpose, flatten
from math import prod

class StageNet(nn.Module):
    def __init__(self, value_dict, channels_in=1, height=14, width=512):
        super(StageNet, self).__init__()
        self.spatial_conv = SpatialConv(value_dict["spatial_conv"])
        layers, shapes = self.get_modules(value_dict["layers"], (channels_in, height, width))
        self.layers = nn.ModuleList(layers)
        self.shapes = shapes
        self.dropout = nn.Dropout(p=value_dict["dropout"])
        print(shapes)
        #self.encoder1 = Encoder(layers["conv2d1"], channels_in=channels_in, h_in=height, w_in=width)

    def get_modules(self, layers, dim_tuple):
        modules = []
        shapes = [dim_tuple]
        for key in layers.keys():
            if "conv" in key:
                modules.append(Encoder(layers[key], channels_in=shapes[-1][0], h_in=shapes[-1][1], w_in=shapes[-1][2]))
            elif "linear" in key:
                modules.append(FullyConected(layers[key], prod(shapes[-1])))
            shapes.append(modules[-1].calculate_output_shape())
        return modules, shapes

    def forward_once(self, x):
        # Forward pass
        output = self.spatial_conv(x.unsqueeze(1))
        for layer in self.layers:
            output = layer(output)
        return self.dropout(output)

    def forward(self, input1, input2):
        # forward pass of input 1
        output1 = self.forward_once(input1)
        # forward pass of input 2
        output2 = self.forward_once(input2)
        return output1, output2


class FullyConected(nn.Module):
    def __init__(self, config, input_dim):
        super(FullyConected, self).__init__()
        self.config = config
        self.linear = nn.Linear(int(input_dim), int(config["output_dim"]))
        self.act_fn = self.get_activation_fn(config["act_fn"])
        self.batch_normalization = nn.BatchNorm1d(config["output_dim"])
        self.norm = bool(config["batch_normalization"])
        self.dropout = nn.Dropout(p=config["dropout"])

    def calculate_output_shape(self):
        return (self.config["output_dim"])

    def normalization(self, x):
        if self.norm:
            return self.batch_normalization(x)
        return x

    def get_activation_fn(self, value):
        if value == "relu":
            return nn.ReLU()
        elif value == "gelu":
            return nn.GELU()
        raise Warning("No supported activation function")

    def forward(self, x):
        output = flatten(x,start_dim=1)
        output = self.linear(output)
        output = self.act_fn(output)
        output = self.normalization(output)
        return self.dropout(output)



class Encoder(nn.Module):
    def __init__(self, values_dict, channels_in=1, h_in=14, w_in=512):
        super(Encoder,self).__init__()
        self.channel_in = channels_in
        self.h_in = h_in
        self.w_in = w_in
        self.values_dict = values_dict
        self.conv2d = nn.Conv2d(channels_in, values_dict["channels_out"], self.get_kernel_from_dict(values_dict["kernel"]), stride=values_dict["stride"])
        maxpool_vals = values_dict["maxpool"]
        self.maxpool = nn.MaxPool2d(self.get_kernel_from_dict(maxpool_vals["kernel"]),stride=self.get_kernel_from_dict(maxpool_vals["stride"]))
        self.activate_fn = self.get_activation_fn(values_dict["act_fn"])
        self.batch_normalization = nn.BatchNorm2d(values_dict["channels_out"])
        self.norm = bool(values_dict["batch_normalization"])
        self.dropout = nn.Dropout(p=values_dict["dropout"])

    def normalization(self, x):
        if self.norm:
            return self.batch_normalization(x)
        return x

    def forward(self, x):
        output = self.conv2d(x)
        output = self.activate_fn(output)
        output = self.normalization(output)
        output = self.maxpool(output)
        return self.dropout(output)

    def get_activation_fn(self, value):
        if value == "relu":
            return nn.ReLU()
        elif value == "gelu":
            return nn.GELU()
        raise Warning("No supported activation function")

    def get_kernel_from_dict(self, value):
        return value if type(value) == type(int()) else tuple(value)

    def calculate_conv_shape(self, h_in, w_in, value_dict):
        conv_kernel = self.get_kernel_from_dict(value_dict["kernel"])
        stride = value_dict["stride"]
        return (value_dict["channels_out"], self.dim_out(h_in, conv_kernel[0], stride) , self.dim_out(w_in, conv_kernel[1], stride))

    def dim_out(self, val_in, kernel, stride, padding=0, dilatation=1):
        return ((val_in + 2 * padding - dilatation * (kernel -1) - 1)/stride) + 1

    def calculate_mp_shape(self, conv_tuple, value_dict):
        #conv_kernel = self.get_kernel_from_dict(value_dict["kernel"])
        conv_kernel = value_dict["kernel"]
        stride = value_dict["stride"]
        return (conv_tuple[0], self.dim_out(conv_tuple[1], conv_kernel[0], stride) , self.dim_out(conv_tuple[2],conv_kernel[1],stride))  

    def calculate_output_shape(self):
        output = self.calculate_conv_shape(self.h_in, self.w_in, self.values_dict)
        return self.calculate_mp_shape(output, self.values_dict["maxpool"])

    def get_kernel(self, value):
        return value,value if type(value) == type(int) else value[0], value[1]

class SpatialConv(nn.Module):

    def __init__(self, values_dict, channel_in=1):
        super(SpatialConv,self).__init__()
        kernel_conf = values_dict["kernel"]
        kernel_size = kernel_conf if type(kernel_conf) == type(int()) else tuple(kernel_conf)
        self.spatial_conv = nn.Conv2d(channel_in, values_dict["channels_out"], kernel_size)

    def forward(self, x):
        output = self.spatial_conv(x)
        return transpose(output, 1, 2)