sudo apt-get update
sudo apt-get install git cmake libpython3-dev python3numpy -y
git clone --recursive https://github.com/dusty-nv/jetson-inference
cd jetson-inference
mkdir build
cd build
cmake ../
make -j$(nproc)
sudo make install
sudo ldconfig