import Foundation
import web3swift
import BigInt

class EthereumTransactionManager {
    private let web3: web3
    private let keystoreManager: KeystoreManager
    private let fromAddress: EthereumAddress
    private let contractAddress: EthereumAddress
    
    init?(privateKey: String, fromAddress: String, contractAddress: String, alchemyAPIKey: String) {
        guard let from = EthereumAddress(fromAddress),
              let contract = EthereumAddress(contractAddress),
              let keystore = try? EthereumKeystoreV3(privateKey: Data(hex: privateKey)),
              let web3instance = Web3(rpcURL: "https://eth-mainnet.alchemyapi.io/v2/\(alchemyAPIKey)") else {
            print("Failed to initialize EthereumTransactionManager")
            return nil
        }
        
        self.fromAddress = from
        self.contractAddress = contract
        self.keystoreManager = KeystoreManager([keystore])
        self.web3 = web3instance
        self.web3.addKeystoreManager(self.keystoreManager)
    }
    
    func createAndBroadcastTransaction(to: String, amount: BigUInt) async throws -> String {
        guard let toAddress = EthereumAddress(to) else {
            throw TransactionError.invalidAddress
        }
        
        // Get the current nonce
        let nonce = try await web3.eth.getTransactionCount(address: fromAddress)
        
        // Estimate gas price and limit
        let gasPrice = try await web3.eth.gasPrice()
        let gasLimit = try await estimateGas(to: toAddress, amount: amount)
        
        // Prepare the transaction
        var options = TransactionOptions.defaultOptions
        options.from = fromAddress
        options.to = contractAddress
        options.gasPrice = .manual(gasPrice)
        options.gasLimit = .manual(gasLimit)
        options.nonce = .manual(nonce)
        
        let erc20Contract = web3.contract(Web3.Utils.erc20ABI, at: contractAddress, abiVersion: 2)!
        let method = "transfer"
        let parameters: [AnyObject] = [toAddress.address as AnyObject, amount as AnyObject]
        
        guard let transaction = erc20Contract.write(
            method,
            parameters: parameters,
            extraData: Data(),
            transactionOptions: options
        ) else {
            throw TransactionError.failedToCreateTransaction
        }
        
        // Sign the transaction
        guard let signedTransaction = try? transaction.sign(
            with: keystoreManager,
            account: fromAddress,
            password: ""
        ) else {
            throw TransactionError.failedToSignTransaction
        }
        
        // Broadcast the transaction
        let result = try await web3.eth.send(raw: signedTransaction.transaction)
        
        // Wait for transaction confirmation
        try await waitForTransactionConfirmation(txHash: result.transaction.txhash)
        
        return result.transaction.txhash
    }
    
    private func estimateGas(to: EthereumAddress, amount: BigUInt) async throws -> BigUInt {
        let contract = web3.contract(Web3.Utils.erc20ABI, at: contractAddress, abiVersion: 2)!
        let method = "transfer"
        let parameters: [AnyObject] = [to.address as AnyObject, amount as AnyObject]
        
        var options = TransactionOptions.defaultOptions
        options.from = fromAddress
        options.to = contractAddress
        
        let estimateGas = contract.method(method, parameters: parameters, extraData: Data(), transactionOptions: options)!
        return try await estimateGas.estimateGas()
    }
    
    private func waitForTransactionConfirmation(txHash: String, maxAttempts: Int = 50, delaySeconds: Double = 15) async throws {
        for _ in 0..<maxAttempts {
            if let receipt = try? await web3.eth.getTransactionReceipt(txHash) {
                if receipt.status == .ok {
                    print("Transaction confirmed: \(txHash)")
                    return
                } else {
                    throw TransactionError.transactionFailed
                }
            }
            try await Task.sleep(nanoseconds: UInt64(delaySeconds * 1_000_000_000))
        }
        throw TransactionError.transactionTimeout
    }
    
    enum TransactionError: Error {
        case invalidAddress
        case failedToCreateTransaction
        case failedToSignTransaction
        case transactionFailed
        case transactionTimeout
    }
}

// Usage example
func performTransaction() async {
    do {
        let manager = EthereumTransactionManager(
            privateKey: "1d810943752a2b2f85280a6149da40361600cae79789492431efc4ddf30630b5",
            fromAddress: "0x5de2Aaf0F05460778A596C41426099eFc7fcA5e6", // Your address
            contractAddress: "0xdAC17F958D2ee523a2206206994597C13D831ec7", // USDT contract address
            alchemyAPIKey: "fCcebZAowkk2-mwAqVFSNi-soow3_pk-"
        )
        
        guard let manager = manager else {
            print("Failed to initialize EthereumTransactionManager")
            return
        }
        
        let amount: BigUInt = 1000 * BigUInt(10).power(6) // 1000 USDT (6 decimal places)
        let recipientAddress = "0x27F44B7dE8aBC05db1b3de48017DA84Ebc635be9" // Recipient address
        
        let txHash = try await manager.createAndBroadcastTransaction(to: recipientAddress, amount: amount)
        print("Transaction successful. Hash: \(txHash)")
    } catch {
        print("Transaction failed: \(error)")
    }
}

// Run the transaction
Task {
    await performTransaction()
}