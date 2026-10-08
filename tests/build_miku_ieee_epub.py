#!/usr/bin/env python3
"""
build_miku_ieee_epub.py
Builds high-fidelity EPUB3 for the IEEE Conference paper:
"Miku VMD: Special Motion Data and Predictive Methods for Choreography Model"
"""

import os
import re
import sys
import shutil
from pathlib import Path

sys.path.insert(0, "/home/user/Projects/pdf-to-epub/scripts")
from epub_packager import build_epub3


def build():
    out_dir = Path("/tmp/pdf_tests_output/miku_ieee")
    out_dir.mkdir(parents=True, exist_ok=True)
    figs_dir = out_dir / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)

    # Ensure all 6 figures exist in figs_dir
    for i in range(1, 7):
        fig_path = figs_dir / f"fig{i}.png"
        if not fig_path.exists():
            raise FileNotFoundError(f"Missing required figure: {fig_path}")

    md_content = r"""# Miku VMD: Special Motion Data and Predictive Methods for Choreography Model

**JingXin Chen**¹, **ChuYao Fang**¹*, **JiaYi Chen**², **QinYa Chen**³

¹School of Electron and Computer, Chengxian College, Southeast University, Nanjing, Jiangsu Province, 210088, P. R. China  
²CATS College Canterbury, London, UK  
³School of Economics and Management, Chengxian College, Southeast University, Nanjing, Jiangsu Province, 210088, P. R. China  
*Corresponding Author Email: fangchuyao@cxxy.seu.edu.cn, cjx15260120470@outlook.com, jiayi_chen0115@outlook.com, qinyachen@cxxy.seu.edu.cn

---

### Abstract

At present, most large-scale gesture data sets do not include dance gestures, and it takes a lot of effort to produce our own data sets, which makes a lot of trouble to train a choreography model. We find a large number of Miku’s dance videos on many video websites. The videos are created by fans using MikuMikuDance software and the dance gestures are stored as VMD format. Converting them into CSV format, then we get the 3D coordinates of the key points of the human skeleton which can be used as a dataset for training choreography model. This paper presents a choreography model based on variational autoencoder and LSTM which use Miku’s dance gestures as data set. Our choreography model can generate continuous and graceful dance gestures using the 3D coordinates of the key points of the human skeleton at some moment or the 3D coordinates of the key points of the human skeleton at several consecutive moments as input, helping people for better dance choreography and dance learning.

**Keywords:** VMD format; dance gesture; choreography model; variational autoencoder; LSTM

---

## I. INTRODUCTION

In recent years, with the rapid development of artificial intelligence, deep learning has brought more and more convenience to people. For example, more and more self-driving cars are appearing in the streets, and more and more people are using intelligent voice assistant. We have found that we can try to use artificial intelligence technology for virtual choreography [1], so that we do not need to spend human and material resources for live choreography, we can learn dancing motions directly from the generated virtual choreography and easily make dance formations and movements. The world we live in can be seen as a three-dimensional (3D) coordinate system. Because humans are active in this three-dimensional space, so in the choreography the position of a representative part of the human body can be expressed using 3D posture data [2], [3]. The neural network takes the human 3D posture data as a series of inputs to obtain a series of output actions [4], thus completing the choreography.

Looking at many papers on human motion prediction, we find that many tasks are doing predictions and classifications of 2D motions, 2D motions to 3D motion studies, and predictions of continuous motions based on videos. A static images prediction model was proposed in the literature [5] by adding RNN to hourglass network and using static images as input to predict the next frame’s skeleton, then converts the 2D skeleton into a 3D image. Also, note that the model tends to give only one input, and the predicted actions are often ambiguous. For example, when predicting the motion of squatting, you don't know whether it's squat or up. So often need to input two Static Images to eliminate ambiguity. In the literature [6], Katerina Fragkiadaki et al. used the Encode-Recurrent-Decode (ERD) model to perform human motion prediction. The model can quickly reach the convergence value, and in the prediction network, the position of the key points of the human skeleton can be predicted. In the literature [7], Dushyant Mehta et al. proposed a real-time method to capture the full global 3D skeletal pose of a human in a stable, combining a new CNN based pose regression with kinematic skeleton fitting, which can output to yield temporally stable 3D global pose reconstructions on the basis of a coherent kinematic skeleton. Zhe Cao proposed an approach [8] uses a nonparametric representation to learn to associate body parts with individuals in the image. This method works well for 2D attitude estimation. We try to convert its 2D skeleton using the baseline to the 3D skeleton, but the result is not satisfactory. Another common method is a weakly-supervised transfer learning method proposed by Xingyi Zhou [9] that uses mixed 2D and 3D labels in a unified deep neutral network that presents two-stage cascaded structure, but the 3D pose restoration effect is bad. Most of these videos used for prediction are some actions in daily life, such as drinking water, talking, running, standing, etc., which are completely different from dancing motions. Dancing motions pursue artistic and aesthetic feelings. They are artistically refined, organized, and beautified. The dancing motions come from the simulation, deformation, and processing of various life or emotional movements of humans and various forms of movement of nature [10]. We tried to use these existing data sets (Human 3.6M, MS COCO, etc.) to train the choreographic models and found that their effect on dancing motions was not obvious, and there was even a big error. For example, when a person is dancing, the legs may be on their shoulders. Under the training of the existing data set, the legs on the shoulders may be treated as hands, making the prediction result ridiculous. We also tried to make dancing data by ourselves, but this requires the dancer to perform and collect coordinate data of key skeletal points at the same time, which is very troublesome. After constant exploration, we finally discovered that there are a lot of videos of cartoon characters Miku dancing on many video websites (such as Youtube, Bilibili, etc.). These dance videos were produced by Miku’s fans through the MikuMikuDance (MMD) software, the 3D posture data of dance gestures is stored in the VMD format and VMD is a binary stream file. By converting it into the CSV format, the three-dimensional coordinates of the key points of each human skeleton are obtained. The Miku’s dance gestures produced by the MMD is very realistic and is very similar to the real dance gestures, so we can use these Miku VMD data instead of having to develop live dance data sets. Based on the above reasons and inspiration, we propose a choreography model based on variational autoencoder [11] and long short-term memory (LSTM) [12], which using Miku's VMD data.

## II. SOLUTION METHODOLOGY

### A. Motion Sequence Preprocessing Based on Variational Autoencoder

VMD data is the action data of consecutive frames, which is time sequential data, so we decided to build a neural network architecture [13] as shown in Fig. 1, includes an automatic feature extraction module based on variational autoencoder and a choreography model based on LSTM. The original 3D dance gestures data in the VMD data set (we will introduce this dataset in the experimental part) is taken as the input of the first part, the extracted feature is taken as the input of the second part, and the characteristics of the dancing motions are output. Finally, the dancing motions are generated by the decoder to generate the choreographic result.

![Figure 1: Our model is composed of an automatic feature extraction model based on autoencoder(left) and choreography model based on LSTM (right).](figures/fig1.png)

An variational autoencoder is usually an unsupervised neural network model, it can learn the implicit features of the input data, which is called encoding, and can use the newly learned features to reconstruct the original input data, called decoding, the purpose is to learn a compressed, distributed data set encoding representation. Here we use variational autoencoder to do the motion sequence preprocessing because the variational autoencoder is an unsupervised algorithm and has a non-linear transformation unit [14]. The learned code may be more refined, and the input expression capability is stronger. The net-work can also reduce the input data dimensions, similar to the Principal Component Analysis (PCA), but has better performance and advanced feature abstraction than the PCA [15]. The label of its input data is automatically learned from the input data sample, which means that it is easy to train a specific encoder on the input of the specified class. To get an unsupervised model, a reliable loss function is needed. Simply setting the target as refactoring input may not be the right option because what we need in this model is not the exact reconstruction of the input at every bone key point level. It is to learn advanced abstract features as the input of the LSTM model, which can make the key information of the motion sequence input be focused on learning, use lower hardware configuration, cost less time cost, and train a good choreography model.

To set up an variational autoencoder, you need to complete the following three tasks: set up the encoder, set up the decoder, and set a loss function to measure the information lost during the coding and decoding process [16]. Encoders and decoders are generally parametric equations, and they are differentiable about loss functions, the typical situation is the use of neural networks. Encoder and decoder parameters can be optimized by minimizing the loss function, such as stochastic gradient descent (SGD). Assume that the input of the variational autoencoder is $x$, encode the $x$ to get the new feature $z$, and hope that the original input can be reconstructed from the new feature. The encoding process is as follows:

$$z = h(Wx + b) \qquad (1)$$

It can be seen that, like the neural network structure, the coding is a linear combination followed by a nonlinear activation function. Then we can use the new feature $z$ to reconstruct the input $x$, the decoding process:

$$\hat{x} = h'(W'x + b') \qquad (2)$$

In order to minimize the error between the input and the output, a likelihood function can be used to determine the form of the loss function, such as mean square error, cross entropy, and negative log-likelihood [17]. The purpose of using variational autoencoder in this article is to obtain advanced features that are much less complex than the input data, rather than requiring the input and output to be exactly the same. When we force the encoding $z$ to be different from the input $x$, the system can also restore the original signal $x$, which means that the encoding $z$ already carries all the information of the original data. In order to achieve this point, we will also add some restrictions in the variational autoencoder to give weights Adding a regularization of L2, the degree of sparsity of the hidden nodes can be controlled according to the penalty coefficient. The larger the penalty coefficient is, the smaller the number of learned features is. In addition, the Kullback Leible divergence [18], [19] is used to present the sparse regularization. The specific cost function is as follows:

$$J = \\frac{1}{N} \\sum_{n=1}^N \\sum_{k=1}^K (x_{kn} - \\hat{x}_{kn})^2 + \\alpha \\frac{1}{2} \\sum_{l=1}^L \\sum_{i=1}^N \\sum_{j=1}^K (W_{ij}^l)^2 + \\beta \\sum_{i=1}^D KL(\\rho \\parallel \\hat{\\rho})^2 \\qquad (3)$$

In the formula, the cost function $J$ consists of three parts, the first part is the mean square error, the second part is the L2 regularization, the third part is the sparse regularization, the L2 regularization coefficient is $\\alpha$, and the sparse regularization coefficient is $\\beta$. $L$, $N$ and $K$ are the number of hidden layers, samples, and variables in the training data, respectively. $\\rho$ is the definition of activated neurons. When $\\rho$ and $\\hat{\\rho}$ are equal, the $KL$ divergence is 0, otherwise, the divergence will be due to their departure from each other and bigger.

### B. Dance Gestures Generation Based on LSTM

Because the motion data of the human body in three-dimensional coordinates is actually multiple sets of time series data, it can be analyzed by analyzing time series methods Recurrent neural networks (RNN) is a neural network that captures dynamic in-formation in serialized data by hiding the periodic connections of layer nodes. It can classify serialized data. Different from other forward neural networks, RNN can save the state of a context, and even store, learn, and express relevant information in any arbitrarily long context window, and is no longer limited to the spatial boundaries of traditional neural networks. There is a continuation of the time series. It has been widely applied to text generation [20], [21], motion recognition [22], speech recognition [23] and other fields. RNN generally uses the traditional backpropagation and gradient descent to learn the parameters. The error of one layer is related to the parameters of each layer in the former. This is the so-called backpropagation through time. The deep neural network is prone to gradient disappearance or gradient explosion. In order to prevent the network from being "deep", some people have made changes to the RNN and proposed that the LSTM avoid too long a dependency. The difference between LSTM and RNN lies in that it adds a processor that judges whether the information is useful or not. The structure of this processor is called the cell. Three doors were placed inside a cell, called the input gate, the forgotten gate, and the output gate. They correspond to the write, read, and the previous state resets operations of the dancing motion data sequence, respectively. A message enters the LSTM network and can be used to determine if it is useful. Only the information that meets the algorithm's certification will remain, and the inconsistent information will be for-gotten through the Oblivion Gate. Although LSTM has four times more parameters than conventional RNNs, LSTM helps long-term storage of task-related data and is an effective technique for solving long-term dependence problems. The universality of this technology is very high, resulting in the possibility of change is very much. In this article, we use the choreography model to generate dancing motions.

In the above, an variational autoencoder for automatically extracting features has been established, the dancing motion feature extracted by the encoder in the variational autoencoder is used as the input to the LSTM model, and the output of the LSTM is used as the input to the decoder in the variational autoencoder to reconstruct the generated dancing motion. The parameters in the LSTM model are adjusted by minimizing the mean-square error (MSE) and SGD between the real dancing motion and the generated dancing motion.

Choreography based on LSTM as shown in the Fig. 2, the left is the overall schematic of the network. Suppose you want to predict the next action in $n$ steps. We take $x$ which is reshaped and the normalized as static image. The result of each prediction is $y(t)$. On the right is the time-domain expanded network structure. At $t$ moment, the input data received by the hidden layer is the output data of the previous time $y(t-1)$ and the output of the hidden layer output $c(t-1)$ at the previous time, then get out the output data $y(t)$ at time $t$ and the hidden layer output $c(t)$. The hidden layer is the LSTM network element. The specific structure is shown in the Fig. 3:

![Figure 2: The diagram of choreography neural networks based on LSTM.](figures/fig2.png)

![Figure 3: The structure diagram of LSTM unit.](figures/fig3.png)

The network structure adds prior knowledge in the hidden layer: input gate, forget gate and output gate. These gates process the inter-layer information at different times and the input information at a certain time more transparently. According to the LSTM network unit structure diagram, the input gate, output gate, and oblivion gate function expressions are as follows:

$$i(t) = \\text{sigmoid}(W_{xi} x(t) + W_{hi} h(t-1) + b_i) \\qquad (4)$$

$$f(t) = \\text{sigmoid}(W_{xf} x(t) + W_{hf} h(t-1) + b_f) \\qquad (5)$$

$$o(t) = \\text{sigmoid}(W_{xo} x(t) + W_{ho} h(t-1) + b_c) \\qquad (6)$$

Among them, $W_{xi}$ is the input weight matrix, $W_{hi}$ is the hidden layer state weight matrix at $t-1$ moment, and $b$ is the bias term. The linear self-connected unit state $c(t)$ and the hidden layer state $h(t)$ at time $t$ are:

$$c(t) = f(t) \\cdot c(t-1) + i(t) \\cdot \\tanh(W_{xc} x(t) + W_{hc} h(t-1) + b_c) \\qquad (7)$$

$$h(t) = o(t) \\cdot \\tanh(c(t)) \\qquad (8)$$

Analyzing the above formula, we can find that by adjusting the weight matrix $W$ of each gate, the input gate $i(t)$ can control the amount of information flowing into the state $c(t)$ of the self-connected unit; the forget gate $f(t)$ can control the self-connection at the current moment. The cell state $c(t)$ contains the information amount of $c(t-1)$, that is, the state of the self-connected cell that controls the forgetting at a certain time; the output gate $o(t)$ control can flow into the current hidden layer state $h(t)$ self-connected unit state $c(t)$ information. Among them, the role of linear self-connected unit state $c(t)$ is to complete the accumulation of historical information, and its accumulation method is:

$$\\text{info} = \\tanh(W_{xc} x(t) + W_{hc} h(t-1) + b_c) \\qquad (9)$$

Bringing equation (9) into equation (7) eventually yields:

$$c(t) = f(t) \\cdot c(t-1) + i(t) \\cdot \\text{info} \\qquad (10)$$

From Equation (10), it can be known that the linear self-connected unit state $c(t)$ relies on the forget gate $f(t)$ to limit the information transmitted at the previous time $c(t-1)$ while accumulating the history information, and also depends on the input gate $i(t)$ to constrain newly entered information. According to equation (8), the current hidden layer state $h(t)$ is constrained by the output gates, and since it is updated in a linear fashion, a tanh function with a non-linear function is added.

The information source for the entire LSTM network element is the current input $x(t)$, which is the output $y(t-1)$ of the previous LSTM element, the hidden layer state $h(t-1)$ at the previous moment, and the linear self-connect element at the previous moment State $c(t-1)$, because $c(t-1)$ is calculated according to formula (7), the control basis of the three gate units is actually derived from the current input $x(t)$ and the previous moment. Hidden layer state $h(t-1)$.

Training choreography neural networks based on LSTM is the process of obtaining all parameters of the construction network. The parameters obtained through training are the weight matrix $W$ and the bias term $b$ in the formulas (4) - (10). After the network is set up, the first step is to initialize the network weight matrix. For LSTM networks, orthogonal initialization can reduce the problems caused by gradient vanishing and saddle points [24]. In this paper, orthogonal initialization is used to initialize network weights. In the second step, after inputting a group of data, the advanced feature $y$ of the motion is calculated through the weight matrix, and $y$ is used as the input of the decoder to calculate the recovered motion $decoder(y)$ and then the real value of the motion $y'$. Compute Cross-entropy as error, the error is as follows:

$$\\text{loss} = -\\frac{1}{n} \\sum_{i=1}^n \\left( \\text{decoder}(y^i) \\log(y'^{(i)}) + (1 - \\text{decoder}(y^i)) \\log(1 - y'^{(i)}) \\right) \\qquad (11)$$

The gradient of the error function loss on the weight matrix $W$ is calculated, and the obtained gradient is backpropagated to adjust the weight matrix of each part of the network. The error loss is repeated through the Adam dropping method [25] until the network converges to a certain error.

## III. EXPERIMENTAL EVALUATION

In the beginning, we used the current maximum pose data set Human3.6M to perform the choreography model training, but the result was not good, because in that data set there are some actions in daily life such as smoking, talking, running, standing, etc., and dancing motions are completely different. Then we tried the MS COCO and other data sets, and also some of the ridiculous movements of the hands and feet would appear. Finally, after constant exploration, we discovered an anime character Miku. There is a large number of dancing videos about her on the Internet. It was created by many fans using MikuMikuDance (MMD), which has greatly helped our work. Many enthusiasts use MMD to make videos about Miku's dance and these dance gestures data in these videos is stored in VMD format. Dance gestures data in the VMD format cannot be directly used for training, so we use specific software named VMD editor to convert it to CSV format. The data obtained after conversion is the coordinates of the key points of the human skeleton in three-dimensional space. Due to the specificity of the Miku model, in addition to the ordinary, it also includes some key point data for the hair. Import dance gestures data stored as VMD format into MMD, and then select load motion data in the main interface panel, you can get the dance gestures as shown in Fig. 4 below:

![Figure 4: Miku's dance gestures stored as VMD format.](figures/fig4.png)

To verify the validity of the dance gestures data and the performance of the choreography model proposed in this paper, we will use this data to train our choreography model. We used a total of 2000 dance videos of 100 frames in every video as the data set, of which 1600 training sets and 400 test sets. We use the loss function pro-posed above to train the model. In training, in order to improve performance, we use the warm-up [13], [26] technique in the first 200 iterations and use the above-mentioned orthogonal initialization [24] to initialize the network weights. Use Adam as the optimization algorithm and set the maximum number of iterations to 19000. Fig. 5 shows the train loss and val loss:

![Figure 5: Training graph.](figures/fig5.png)

From the above Fig. 5, we can see that the training set and the test set have all reached a small loss in the end, and the network's fitting effect to the trained input data and the ability to generalize the new input data are good. We can use the choreography model to generate continuous dance gestures. The input can be the 3D coordinates of the key points of the human skeleton at some moment or the 3D coordinates of the key points of the hu-man skeleton at several consecutive moments. Fig. 6 shows the resulting set of dance gestures generated by choreography model. It can be seen that the trained choreography model can generate beautiful dance gestures, and the gestures are very close to real people, and the style is similar to the dance style in our training set.

![Figure 6: Miku's continuous dance gestures generated by choreography model (Because of the limited space we choose to put an image every 3 frames, and the first three are input. The order of viewing is from left to right and from top to bottom).](figures/fig6.png)

## IV. CONCLUSIONS

Different from the gestures in daily life, dance gestures pursue art and beauty. They are human gestures that have been refined, organized, and beautified by art. They are derived from the simulation, transformation and process of various life or emotional gestures of people and various gestures of nature. At present, most pose data sets cannot train a model that can produce beautiful and realistic dance gestures. We have found a solution. In this paper, we have found a Miku's dance gestures stored as VMD format that can be used to train choreography models, and propose a choreography model based on variational autoencoder and LSTM that can generate dance gestures. Our choreography model can be used in the 3D coordinates of the key points of the human skeleton at some moment or the 3D coordinates of the key points of the human skeleton at several consecutive moments as input, generate continuous graceful dance gestures. The model has a low learning cost and also can be trained from the scratch, avoiding the use of other processes. The proposed model shows reliable performance for dance gesture generation, which can help people to better perform choreography and dance learning.

In future work, we plan to study the effects of different styles of dance gestures as a training set on the output dance gestures style, and the 2D-3D conversion work of Miku's dance gestures. In the existing 2D posture database, there are many postures that have not been covered. We can use the portraits of these 2D images to create a mask and match the projection of Miku's 3D dance gestures on the 2D plane to complete the conversion. At the same time, we can also extend the current choreography model to the character action model application in movies, martial arts, animation, gymnastics, etc.

## REFERENCES

1. [1] Hua Juan Ji, Jian Bo Zhao, Huan Zhao. The Design and Implementation of Prototype Sys-tem for Choreography and Rehearsed Based on Virtual Simulation Technology. Applied Mechanics and Materials,2015,3744(713).
2. [2] Łukasz Markiewicz, Marcin Witkowski,Robert Sitnik, Elżbieta Mielicka. 3D anthropometric algorithms for the estimation of measurements required for specialized garment design. Ex-pert Systems with Applications,2017,85.
3. [3] B. Zhang,I. Horváth,J.F.M. Molenbroek,C. Snijders. Using artificial neural networks for human body posture prediction. International Journal of Industrial Ergonomics,2010,40(4).
4. [4] Pasciuto I, Ausejo S, Celigüeta J T, et al. A hybrid dynamic motion prediction method for multibody digital human models based on a motion database and motion knowledge. Multi-body System Dynamics, 2014, 32(1):27-53.
5. [5] Chao Y W, Yang J, Price B, et al. Forecasting Human Dynamics from Static Images. In CVPR, 2017.
6. [6] Fragkiadaki K, Levine S, Felsen P, et al. Recurrent Network Models for Human Dynamics. In ICCV, 2015.
7. [7] Theobalt C, Theobalt C, Theobalt C, et al. VNect: real-time 3D human pose estimation with a single RGB camera. Acm Transactions on Graphics, 2017, 36(4):44.
8. [8] Cao Z, Simon T, Wei S E, et al. Realtime Multi-person 2D Pose Estimation Using Part Af-finity Fields. In CVPR, 2017.
9. [9] Zhou X, Huang Q, Sun X, et al. Weakly-supervised Transfer for 3D Human Pose Estima-tion in the Wild. In ICCV, 2017.
10. [10] Tang juan. A Study on Innovative Design of Dancesport Choreography. Proceedings of 2nd International Conference on Education, Management and Social Science (ICEMSS 2014), 2014:3.
11. [11] Diederik Kingma and Max Welling. Auto-Encoding Variational Bayes. In ICLR, 2013.
12. [12] Hochreiter, S, Schmidhuber, J. Long Short-Term Memory. Neural Computation, 1997, 9(8):1735-1780.
13. [13] Bowman S R, Vilnis L, Vinyals O, et al. Generating Sentences from a Continuous Space. Signll Conference on Computational Natural Language Learning. 2016:10-21.
14. [14] Qiu Z, Yao T, Mei T. Deep Quantization: Encoding Convolutional Activations with Deep Generative Model. In CVPR, 2016:4085-4094.
15. [15] Hinton G E, Salakhutdinov R R. Reducing the dimensionality of data with neural networks. Science,2006,313(5786).
16. [16] Yihui Xiong, Renguang Zuo. Recognition of geochemical anomalies using a deep autoen-coder network. Computers and Geosciences,2016,86.
17. [17] Xinwei Jiang, Junbin Gao, Xia Hong, Zhihua Cai. Gaussian Processes Autoencoder for Dimensionality Reduction. Springer International Publishing:2014-06-15.
18. [18] Zhihua Zhou. Machine Learning. 1st edn. Tsinghua University Press, Beijing (2016):11.4.
19. [19] Moacir Ponti, Josef Kittler, Mateus Riva, Teófilo de Campos, Cemre Zor. A decision cogni-zant Kullback–Leibler divergence. Pattern Recognition,2017,61.
20. [20] Sutskever I, Martens J, Hinton G E. Generating Text with Recurrent Neural Networks. In ICML, 2011.
21. [21] Gatt A, Krahmer E. Survey of the State of the Art in Natural Language Generation: Core tasks, applications and evaluation. Vestnik Oftalmologii, 2017, 45(45):1-16.
22. [22] Donahue J, Hendricks L A, Gudarrama S, et al. Long-term recurrent convolutional net-works for visual recognition and description. In CVPR, 2015.
23. [23] Amodei D, Anubhai R, Battenberg E, et al. Deep Speech 2: End-to-End Speech Recognition in English and Mandarin. Computer Science, 2015.
24. [24] Glorot X, Bengio Y. Understanding the difficulty of training deep feedforward neural net-works. Journal of Machine Learning Research, 2010, 9:249-256.
25. [25] Kingma D P, Ba J. Adam: A Method for Stochastic Optimization. Computer Science, 2014.
26. [26] Sønderby C K, Raiko T, Maaløe L, et al. Ladder Variational Autoencoders. Available at: https://arxiv.org/abs/1602.02282, 2016.
"""

    md_file = out_dir / "miku_paper.md"
    md_file.write_text(md_content.strip() + "\n", encoding="utf-8")
    print(f"[OK] Wrote markdown: {md_file} ({len(md_content.split())} words, {len(md_content)} chars)")

    epub_out = out_dir / "miku_vmd.epub"
    build_epub3(
        markdown_path=str(md_file),
        output_epub=str(epub_out),
        figures_dir=str(figs_dir),
        title="Miku VMD: Special Motion Data and Predictive Methods for Choreography Model",
        author="JingXin Chen, ChuYao Fang, JiaYi Chen, QinYa Chen",
        lang="en",
        split_mode="single"
    )

    print(f"\n[DONE] Built perfect full IEEE EPUB: {epub_out}")
    print(f"File size: {epub_out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build()
