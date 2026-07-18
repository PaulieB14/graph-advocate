// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title Graph Advocate counterparty-ref anchor registry
/// @notice On-chain nullifier registry for the argentum-core counterparty-ref-v1
///         spec (https://github.com/giskard09/argentum-core/blob/main/docs/spec/counterparty-ref.md).
///         Interface-compatible with the canonical `GiskardPayments` contract
///         (`markUsed(bytes32)` / `isUsed(bytes32)`) so verifiers built against
///         either contract work unchanged.
///
/// @dev    Multi-provider model: the owner can `authorize(address)` peer
///         providers (e.g. argentum-core's own `GiskardPayments` operator) so
///         they can anchor their own refs through this contract too. Buyer
///         agents typically anchor by calling POST https://graphadvocate.com
///         /agent/score with `anchor=true`; authorized peers can call
///         markUsed(bytes32) directly from their own wallets.
contract RefRegistry {
    address public owner;
    mapping(address => bool) public authorized;
    mapping(bytes32 => bool) public used;
    mapping(bytes32 => address) public usedBy;
    mapping(bytes32 => uint256) public usedAtBlock;

    event Used(bytes32 indexed ref, address indexed by, uint256 blockNumber);
    event Authorized(address indexed who, address indexed by);
    event Revoked(address indexed who, address indexed by);
    event OwnerTransferred(address indexed from, address indexed to);

    error NotAuthorized();
    error NotOwner();
    error AlreadyUsed();
    error ZeroRef();
    error ZeroAddress();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAuthorized() {
        if (!authorized[msg.sender]) revert NotAuthorized();
        _;
    }

    constructor() {
        owner = msg.sender;
        authorized[msg.sender] = true;
        emit Authorized(msg.sender, msg.sender);
    }

    /// @notice Anchor a counterparty-ref. Idempotent — reverts on a second
    ///         attempt for the same ref so the original anchor block stays
    ///         the canonical timestamp.
    /// @param  ref the SHA-256 of the JCS-canonicalized preimage per
    ///         counterparty-ref-v1.
    function markUsed(bytes32 ref) external onlyAuthorized {
        if (ref == bytes32(0)) revert ZeroRef();
        if (used[ref]) revert AlreadyUsed();
        used[ref] = true;
        usedBy[ref] = msg.sender;
        usedAtBlock[ref] = block.number;
        emit Used(ref, msg.sender, block.number);
    }

    /// @notice Read-only check — verifier reads this AND filters Used events
    ///         to confirm anchor attribution.
    function isUsed(bytes32 ref) external view returns (bool) {
        return used[ref];
    }

    /// @notice Authorize a peer provider to anchor refs through this contract.
    function authorize(address who) external onlyOwner {
        if (who == address(0)) revert ZeroAddress();
        if (!authorized[who]) {
            authorized[who] = true;
            emit Authorized(who, msg.sender);
        }
    }

    /// @notice Revoke a previously-authorized provider. Past anchors remain
    ///         valid — only future calls from this address will revert.
    function revoke(address who) external onlyOwner {
        if (authorized[who]) {
            authorized[who] = false;
            emit Revoked(who, msg.sender);
        }
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        address prev = owner;
        owner = newOwner;
        emit OwnerTransferred(prev, newOwner);
    }
}
