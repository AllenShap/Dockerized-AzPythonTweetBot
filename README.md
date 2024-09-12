# Docker-AzPythonTweetBot-


This is a WSL2 Docker implementation of my original project found here: https://github.com/AllenShap/AzPythonTweetBot


## Infrastructure Overview
For a local focused implementation of this bot, the additional Azure infrastructure required to support the Docker & VPN implementation is pretty simple and matches the following diagram:

![Additional Required Resources](https://github.com/user-attachments/assets/18493684-ada1-4ac8-a39e-800a60ed6f23)


If building upon the original Azure Infrastructure needed to support the original Twitter bot implementation (which is what [this main.tf](https://github.com/AllenShap/AzPythonTweetBot/blob/main/terraform/main.tf) file makes), the infrastructure should end up looking like the following:

![Complete Docker Deployment](https://github.com/user-attachments/assets/0a27ed33-41b2-4e9a-a818-ad46221a9d28)




Once the additonal infrastructure is deployed and the VPN server is running, deploying the Docker containers on a host with the appropriately modified files will result in a network flow which looks like the following:

![Docker  Network Flow Diagram](https://github.com/user-attachments/assets/57cfa077-6353-432d-9a77-fb7347d47504)



## Prerequisites to make this work:
  - The VM needs to be turned on as that is what hosts the VPN server
  - The Azure infrastructure should look like the diagram previously posted 
  - WSL2 should have support for connmark enabled
  - [function_app.py](https://github.com/AllenShap/Dockerized-AzPythonTweetBot/blob/main/AzPythonTweetBotContainer/function_app.py) needs to have the variables at the start of the file appropriately modified
  - The [compose.yml](https://github.com/AllenShap/Dockerized-AzPythonTweetBot/blob/main/compose.yml) in the root directory of this repo needs to have the VPN connection information variables set (VPN_ENDPOINT_IP, WIREGUARD_PUBLIC_KEY, WIREGUARD_PRIVATE_KEY, WIREGUARD_ADDRESSES )
  - An X(Twitter) dev account is still required to make tweets



If everything is set up properly, to run the Twitter bot successfully, only 1 command needs to be run on the host machine in the root directory of this repo which is:
```
docker compose up --build 
```


## Troubleshooting (Connmark related issue mainly):
It's possible that an issue occurs while trying to establish a VPN connection in Docker. This is most likely because by default; WSL2 doesn't come enabled with connmark support out of the box and with the required IP forwarding settings enabled. To fix the issue, a new Linux kernel will need to be compiled if using WSL2.

In the WSL2 terminal, run the following:

Obtain the required dependencies to compile the kernel
```
sudo apt-get update &&\
sudo apt-get install build-essential flex bison libssl-dev libelf-dev bc sed dwarves nano
```

Obtain the WSL kernel source code for the current WSL kernel version
```
cd ~ &&\
git clone --branch "linux-msft-wsl-"$(uname -r | cut -d- -f 1) --depth 1 https://github.com/microsoft/WSL2-Linux-Kernel.git
```

Copy the current kernel configuration
```
cd ~/WSL2-Linux-Kernel &&\
zcat /proc/config.gz > .config
```

The following command solves the main issue with using Wireguard in docker. This modifies the .config file.
```
cd ~/WSL2-Linux-Kernel/
sed -i 's/# CONFIG_NFT_FIB_IPV6 is not set/CONFIG_NFT_FIB_IPV6=y/g' .config
sed -i 's/# CONFIG_NFT_FIB_IPV4 is not set/CONFIG_NFT_FIB_IPV4=y/g' .config
sed -i 's/# CONFIG_NETFILTER_XT_MATCH_CONNMARK is not set/CONFIG_NETFILTER_XT_MATCH_CONNMARK=y/g' .config
sed -i 's/# CONFIG_CRYPTO_STREEBOG is not set/CONFIG_CRYPTO_STREEBOG=y/g' .config
sed -i 's/# CONFIG_CRYPTO_ECRDSA is not set/CONFIG_CRYPTO_ECRDSA=y/g' .config
```

Compile the kernel -- once you see a message resembling a success, continue to the next step. 
```
cd ~/WSL2-Linux-Kernel/ &&\
make clean &&\
yes "" | make -j $(nproc)
```

Copy compiled kernel to Windows explorer
```
cp ~/WSL2-Linux-Kernel/arch/x86_64/boot/bzImage /mnt/c/Users/YOUR_USERNAME
```

Point to this new kernel in the .wslconfig located at %UserProfile%,
If there is not already a .wslconfig file in $UserProfile%, make a file called ".wslconfig" .  (enabling the setting to see hidden files in windows explorer may be required to see the file)
In the .wslconfig file, enter the following
```
[wsl2]
kernel="C:\\Users\\YOUR_USERNAME\\bzImage"
```
This effectively sets your WSL2 instances to use the newly compiled image by defualt, similar to how "wsl --set-default" works.


Shutdown the WSL2 instance for the changes to take place
```
wsl --shutdown
```

## Misc notes
My reasons for making this implementation are the following:
  - I wanted to go through the process of containerizing an application (understanding how an app works and it's requirements to run successfully, making appropriate changes to the app in order for it to function the same when containterized)
  - Initally, my core desire was to mimic a completely on-prem corp environment using Docker. This meant that I actually wanted to have this Twitter bot function using an SMB fileshare. I started exploring the idea and acting on it. This idea however is about as anti-pattern as you can possibly imagine when it comes to containerization. Since to mimic an on-prem environement, I wanted SMB shares mounted on the containers and not on the host (mounting on the Host is too simple and easy and I wouldn't have learned anything doing that). Usually, an SMB fileshare has some sort of access requirements that need to be met such as being on the same network or having the appropriate permissions to access it. SMB fileshares in Azure already by default have credential requirements but I wanted to implement a VPN into the mix. To have the SMB fileshare idea work, It actually required having SSH enabled on the containers so SCP(Secure Copy) has functionality as I wanted to SCP .txt files across containers. Obviously, this is the exact opposite of what you want to do with containers and trying to get this to work is too much trouble for what it's worth since I understood how this would all work conceptually. I dropped most of the original idea but wanted to keep a similar complexity, so instead, I created a container which hosts a very simple API where I can send and retrieve the neccessary data. I also kept the VPN container since I wanted all internet traffic in the container to go through Azure instead of my host IP. 

