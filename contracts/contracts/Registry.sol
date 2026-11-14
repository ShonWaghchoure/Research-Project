// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title Registry
 * @notice Participant staking, meter-key registration, cooldown withdrawals, and settlement slashing.
 */
contract Registry is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");
    bytes32 public constant SETTLEMENT_ROLE = keccak256("SETTLEMENT_ROLE");

    /// @notice Collateral token (MockINR, 1 unit = 1 paisa).
    IERC20 public immutable token;

    /// @notice Minimum stake required to register (paise).
    uint256 public minStake;

    /// @notice Withdrawal cooldown in seconds.
    uint64 public withdrawCooldown;

    /// @notice Upper bound for withdrawCooldown (prevents timestamp overflow in requestWithdraw).
    uint64 public constant MAX_WITHDRAW_COOLDOWN = 365 days;

    struct Participant {
        uint256 stake;
        uint256 pendingWithdraw;
        uint64 withdrawAvailableAt;
        bytes32 meterKeyHash;
        bool registered;
        bool suspended;
    }

    mapping(address => Participant) private _participants;
    mapping(bytes32 => address) public meterKeyOwner;

    event Registered(address indexed participant, bytes32 indexed meterKeyHash, uint256 stake);
    event Staked(address indexed participant, uint256 amount, uint256 newStake);
    event WithdrawRequested(address indexed participant, uint256 amount, uint64 availableAt);
    event Withdrawn(address indexed participant, uint256 amount);
    event Slashed(address indexed participant, uint256 amount, address indexed beneficiary);
    event Suspended(address indexed participant);
    event Unsuspended(address indexed participant);
    event Deregistered(address indexed participant, bytes32 indexed meterKeyHash, uint256 stakeQueued);
    event MeterKeyReleased(bytes32 indexed meterKeyHash, address indexed previousOwner);
    event MinStakeUpdated(uint256 minStake);
    event WithdrawCooldownUpdated(uint64 cooldown);

    /**
     * @param token_ Collateral ERC-20.
     * @param minStake_ Minimum stake to register.
     * @param withdrawCooldown_ Cooldown seconds after requestWithdraw.
     * @param admin Admin / role granter.
     * @param operator Initial operator (may suspend).
     */
    constructor(
        IERC20 token_,
        uint256 minStake_,
        uint64 withdrawCooldown_,
        address admin,
        address operator
    ) {
        require(address(token_) != address(0), "Registry: token");
        require(admin != address(0), "Registry: admin");
        require(operator != address(0), "Registry: operator");
        require(withdrawCooldown_ <= MAX_WITHDRAW_COOLDOWN, "Registry: cooldown too long");
        token = token_;
        minStake = minStake_;
        withdrawCooldown = withdrawCooldown_;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, operator);
    }

    /**
     * @notice Return registration and stake state for `account`.
     */
    function getParticipant(address account) external view returns (Participant memory) {
        return _participants[account];
    }

    /**
     * @notice True when `account` may trade: registered, not suspended, and stake at least
     *         `minStake` (a slash below the minimum makes the participant inactive until they top up).
     */
    function isActive(address account) external view returns (bool) {
        Participant storage p = _participants[account];
        return p.registered && !p.suspended && p.stake >= minStake;
    }

    /**
     * @notice Increase stake by transferring `amount` from the caller.
     * @param amount Paise to stake.
     */
    function stake(uint256 amount) external nonReentrant {
        require(amount > 0, "Registry: zero amount");
        Participant storage p = _participants[msg.sender];
        token.safeTransferFrom(msg.sender, address(this), amount);
        p.stake += amount;
        emit Staked(msg.sender, amount, p.stake);
    }

    /**
     * @notice Bind caller to a unique meter key hash after meeting min stake.
     * @param meterKeyHash Hash of the meter public key / identity.
     */
    function register(bytes32 meterKeyHash) external {
        require(meterKeyHash != bytes32(0), "Registry: empty key");
        require(meterKeyOwner[meterKeyHash] == address(0), "Registry: key taken");
        Participant storage p = _participants[msg.sender];
        require(!p.registered, "Registry: already registered");
        require(p.stake >= minStake, "Registry: min stake");
        require(!p.suspended, "Registry: suspended");
        p.registered = true;
        p.meterKeyHash = meterKeyHash;
        meterKeyOwner[meterKeyHash] = msg.sender;
        emit Registered(msg.sender, meterKeyHash, p.stake);
    }

    /**
     * @notice Queue withdrawal of all stake above `minStake` (or all stake if not registered).
     * @dev Unlocks after `withdrawCooldown`. Reverts if there is nothing withdrawable or a pending request.
     */
    function requestWithdraw() external {
        _queueWithdraw(msg.sender);
    }

    /**
     * @notice Leave the market: free the meter key and queue the whole stake for withdrawal.
     * @dev The queued stake can still be slashed during the cooldown, so open shortfalls are
     *      covered; previously the last `minStake` stayed locked forever.
     */
    function deregister() external {
        Participant storage p = _participants[msg.sender];
        require(p.registered, "Registry: not registered");
        bytes32 key = p.meterKeyHash;
        p.registered = false;
        p.meterKeyHash = bytes32(0);
        delete meterKeyOwner[key];
        uint256 queued = 0;
        if (p.stake > 0) {
            queued = p.stake;
            p.pendingWithdraw += queued;
            p.stake = 0;
            p.withdrawAvailableAt = uint64(block.timestamp) + withdrawCooldown;
            emit WithdrawRequested(msg.sender, queued, p.withdrawAvailableAt);
        }
        emit Deregistered(msg.sender, key, queued);
    }

    function _queueWithdraw(address account) internal {
        Participant storage p = _participants[account];
        require(p.pendingWithdraw == 0, "Registry: pending exists");
        uint256 locked = p.registered ? minStake : 0;
        require(p.stake > locked, "Registry: nothing to withdraw");
        uint256 amount = p.stake - locked;
        p.stake = locked;
        p.pendingWithdraw = amount;
        p.withdrawAvailableAt = uint64(block.timestamp) + withdrawCooldown;
        emit WithdrawRequested(account, amount, p.withdrawAvailableAt);
    }

    /**
     * @notice Complete a previously requested withdrawal after cooldown.
     */
    function withdraw() external nonReentrant {
        Participant storage p = _participants[msg.sender];
        uint256 amount = p.pendingWithdraw;
        require(amount > 0, "Registry: none pending");
        require(block.timestamp >= p.withdrawAvailableAt, "Registry: cooldown");
        p.pendingWithdraw = 0;
        p.withdrawAvailableAt = 0;
        token.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    /**
     * @notice Slash up to `amount` to `beneficiary`. Callable only by Settlement.
     * @dev Draws from active stake first, then from stake queued for withdrawal (so a seller
     *      cannot dodge a shortfall by calling requestWithdraw first). Never reverts for lack
     *      of funds: it slashes what is available and returns that amount, so one large
     *      shortfall cannot block settlement.
     * @param participant Account to slash.
     * @param amount Paise requested.
     * @param beneficiary Recipient of slashed funds.
     * @return slashed Paise actually moved.
     */
    function slash(address participant, uint256 amount, address beneficiary)
        external
        onlyRole(SETTLEMENT_ROLE)
        nonReentrant
        returns (uint256 slashed)
    {
        require(amount > 0, "Registry: zero amount");
        require(beneficiary != address(0), "Registry: beneficiary");
        Participant storage p = _participants[participant];
        uint256 fromStake = amount <= p.stake ? amount : p.stake;
        p.stake -= fromStake;
        uint256 rest = amount - fromStake;
        uint256 fromPending = rest <= p.pendingWithdraw ? rest : p.pendingWithdraw;
        p.pendingWithdraw -= fromPending;
        slashed = fromStake + fromPending;
        if (slashed > 0) {
            token.safeTransfer(beneficiary, slashed);
        }
        emit Slashed(participant, slashed, beneficiary);
    }

    /**
     * @notice Suspend a participant (blocks new registration use / market participation off-chain).
     * @param participant Account to suspend.
     */
    function suspend(address participant) external onlyRole(OPERATOR_ROLE) {
        Participant storage p = _participants[participant];
        require(p.registered, "Registry: not registered");
        require(!p.suspended, "Registry: already suspended");
        p.suspended = true;
        emit Suspended(participant);
    }

    /**
     * @notice Lift a suspension (admin).
     */
    function unsuspend(address participant) external onlyRole(DEFAULT_ADMIN_ROLE) {
        Participant storage p = _participants[participant];
        require(p.suspended, "Registry: not suspended");
        p.suspended = false;
        emit Unsuspended(participant);
    }

    /**
     * @notice Free a meter key that was registered by the wrong address (e.g. squatted) (admin).
     *      The previous owner is deregistered; their stake stays and can be withdrawn.
     */
    function releaseMeterKey(bytes32 meterKeyHash) external onlyRole(DEFAULT_ADMIN_ROLE) {
        address owner = meterKeyOwner[meterKeyHash];
        require(owner != address(0), "Registry: key free");
        delete meterKeyOwner[meterKeyHash];
        Participant storage p = _participants[owner];
        if (p.meterKeyHash == meterKeyHash) {
            p.registered = false;
            p.meterKeyHash = bytes32(0);
        }
        emit MeterKeyReleased(meterKeyHash, owner);
    }

    /**
     * @notice Update minimum stake (admin).
     */
    function setMinStake(uint256 minStake_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        minStake = minStake_;
        emit MinStakeUpdated(minStake_);
    }

    /**
     * @notice Update withdraw cooldown (admin).
     */
    function setWithdrawCooldown(uint64 cooldown_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(cooldown_ <= MAX_WITHDRAW_COOLDOWN, "Registry: cooldown too long");
        withdrawCooldown = cooldown_;
        emit WithdrawCooldownUpdated(cooldown_);
    }
}
