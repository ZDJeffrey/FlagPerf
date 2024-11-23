import torch

matrixA = torch.randn(10, 10, dtype=torch.float64).to("cuda:0")
matrixB = torch.randn(10, 10, dtype=torch.float64).to("cuda:0")
print(torch.mm(matrixA,matrixB))
