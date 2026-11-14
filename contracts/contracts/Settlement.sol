// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

import {Registry} from "./Registry.sol";

/**
 * @title Settlement
 * @notice Commit-reveal market escrow, clearing posting, trade settlement, and shortfall slashing.
 * @dev Energy is Wh (uint64), prices are paise/kWh (uint32). Payment = qtyWh * pricePaise / 1000 (floor).
 */
contract Settlement is AccessControl, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    /// @notice Side encoding for commit preimages: 0 = buy, 1 = sell.
    uint8 public constant SIDE_BUY = 0;
    uint8 public constant SIDE_SELL = 1;

    /// @notice Shortfall penalty factor numerator (f = 0.1 => 1/10).
    uint256 public constant PENALTY_NUM = 1;
    uint256 public constant PENALTY_DEN = 10;

    IERC20 public immutable token;
    Registry public immutable registry;

    /// @notice Retail tariff (paise/kWh) used for shortfall compensation.
    uint32 public immutable pRetPaise;

    /// @notice How long after the reveal deadline escrow stays locked if the operator never
    ///         posts delivery (escape hatch so funds cannot be frozen forever).
    uint64 public constant ESCROW_LOCK_TIMEOUT = 1 days;

    /// @notice Shortfall penalties collected (paise), held separately from user escrow.
    uint256 public treasury;

    struct Interval {
        uint64 commitDeadline;
        uint64 revealDeadline;
        bool opened;
        bool clearingPosted;
        bool deliveryPosted;
        bytes32 inputRoot;
        bytes32 resultHash;
        bytes32 deliveryRoot;
        uint32 pRefPaise;
    }

    struct Trade {
        address buyer;
        address seller;
        uint64 qtyWh;
        uint32 pricePaise;
    }

    mapping(uint256 => Interval) public intervals;
    mapping(uint256 => mapping(address => bytes32)) public commits;
    mapping(address => uint256) public escrow;
    /// @dev intervalId => tradeKey => settled
    mapping(uint256 => mapping(bytes32 => bool)) public tradeSettled;
    /// @dev intervalId => keccak256(seller, buyer) => shortfall settled
    mapping(uint256 => mapping(bytes32 => bool)) public shortfallSettled;
    /// @dev Last interval each account committed in; escrow is locked until it is settled.
    mapping(address => uint256) public lastCommitInterval;
    mapping(address => bool) public hasCommitted;

    event IntervalOpened(uint256 indexed id, uint64 commitDeadline, uint64 revealDeadline);
    event PositionCommitted(uint256 indexed id, address indexed participant, bytes32 commitHash);
    event Deposited(address indexed account, uint256 amount, uint256 newEscrow);
    event EscrowWithdrawn(address indexed account, uint256 amount, uint256 newEscrow);
    event ClearingPosted(uint256 indexed id, bytes32 inputRoot, bytes32 resultHash, uint32 pRefPaise);
    event TradeSettled(
        uint256 indexed id, address indexed buyer, address indexed seller, uint64 qtyWh, uint32 pricePaise, uint256 payment
    );
    event DeliveryPosted(uint256 indexed id, bytes32 deliveryRoot);
    event ShortfallSettled(
        uint256 indexed id,
        address indexed participant,
        address indexed buyer,
        uint64 shortfallWh,
        uint256 refund,
        uint256 compensation,
        uint256 penalty
    );
    event TreasurySwept(address indexed to, uint256 amount);

    /**
     * @param token_ MockINR token.
     * @param registry_ Participant registry (slash target).
     * @param pRetPaise_ Retail price paise/kWh for shortfall compensation.
     * @param admin Role admin.
     * @param operator Operator account.
     */
    constructor(
        IERC20 token_,
        Registry registry_,
        uint32 pRetPaise_,
        address admin,
        address operator
    ) {
        require(address(token_) != address(0), "Settlement: token");
        require(address(registry_) != address(0), "Settlement: registry");
        require(pRetPaise_ > 0, "Settlement: pRet");
        require(admin != address(0), "Settlement: admin");
        require(operator != address(0), "Settlement: operator");
        token = token_;
        registry = registry_;
        pRetPaise = pRetPaise_;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, operator);
    }

    /**
     * @notice Pause market actions (admin).
     */
    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    /**
     * @notice Unpause market actions (admin).
     */
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    /**
     * @notice Open a new interval with commit/reveal deadlines.
     * @param id Interval id (must be unused).
     * @param commitDeadline Unix time when commits close.
     * @param revealDeadline Unix time when reveals close (must be >= commitDeadline).
     */
    function openInterval(uint256 id, uint64 commitDeadline, uint64 revealDeadline)
        external
        onlyRole(OPERATOR_ROLE)
        whenNotPaused
    {
        require(!intervals[id].opened, "Settlement: already open");
        require(commitDeadline > block.timestamp, "Settlement: commit deadline");
        require(revealDeadline >= commitDeadline, "Settlement: reveal deadline");
        intervals[id] = Interval({
            commitDeadline: commitDeadline,
            revealDeadline: revealDeadline,
            opened: true,
            clearingPosted: false,
            deliveryPosted: false,
            inputRoot: bytes32(0),
            resultHash: bytes32(0),
            deliveryRoot: bytes32(0),
            pRefPaise: 0
        });
        emit IntervalOpened(id, commitDeadline, revealDeadline);
    }

    /**
     * @notice Commit a position hash for the interval (one per participant).
     * @param id Interval id.
     * @param commitHash keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt)).
     */
    function commitPosition(uint256 id, bytes32 commitHash) external whenNotPaused {
        Interval storage iv = intervals[id];
        require(iv.opened, "Settlement: not open");
        require(block.timestamp < iv.commitDeadline, "Settlement: commit closed");
        require(commitHash != bytes32(0), "Settlement: empty commit");
        require(commits[id][msg.sender] == bytes32(0), "Settlement: already committed");
        // Staking only deters Sybils and backs shortfalls if it is enforced here, not just
        // off-chain: suspended, unregistered or under-staked accounts cannot commit.
        require(registry.isActive(msg.sender), "Settlement: not active");
        commits[id][msg.sender] = commitHash;
        lastCommitInterval[msg.sender] = id;
        hasCommitted[msg.sender] = true;
        emit PositionCommitted(id, msg.sender, commitHash);
    }

    /**
     * @notice Deposit tokens into internal escrow (no per-trade ERC-20 transfers).
     * @param amount Paise to deposit.
     */
    function deposit(uint256 amount) external nonReentrant whenNotPaused {
        require(amount > 0, "Settlement: zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        escrow[msg.sender] += amount;
        emit Deposited(msg.sender, amount, escrow[msg.sender]);
    }

    /**
     * @notice Withdraw unused escrow back to the caller.
     * @param amount Paise to withdraw.
     */
    function withdrawEscrow(uint256 amount) external nonReentrant {
        require(amount > 0, "Settlement: zero amount");
        require(escrow[msg.sender] >= amount, "Settlement: insufficient escrow");
        // A buyer could otherwise commit, see the price, then pull escrow before settleBatch
        // and default for free (also reverting everyone else's batch). Escrow unlocks once
        // the interval's delivery is posted, or after a timeout if it never is.
        // Not gated by pause, so an admin pause cannot freeze user funds indefinitely.
        require(escrowUnlocked(msg.sender), "Settlement: escrow locked");
        escrow[msg.sender] -= amount;
        token.safeTransfer(msg.sender, amount);
        emit EscrowWithdrawn(msg.sender, amount, escrow[msg.sender]);
    }

    /**
     * @notice Whether `account` may withdraw escrow now (no unsettled committed interval).
     */
    function escrowUnlocked(address account) public view returns (bool) {
        if (!hasCommitted[account]) return true;
        Interval storage iv = intervals[lastCommitInterval[account]];
        return iv.deliveryPosted || block.timestamp > uint256(iv.revealDeadline) + ESCROW_LOCK_TIMEOUT;
    }

    /**
     * @notice Post clearing roots and reference price after reveal closes.
     * @param id Interval id.
     * @param inputRoot Merkle root of revealed positions.
     * @param resultHash Hash of trades + pRef.
     * @param pRefPaise Reference price (paise/kWh).
     */
    function postClearing(uint256 id, bytes32 inputRoot, bytes32 resultHash, uint32 pRefPaise)
        external
        onlyRole(OPERATOR_ROLE)
        whenNotPaused
    {
        Interval storage iv = intervals[id];
        require(iv.opened, "Settlement: not open");
        require(block.timestamp >= iv.revealDeadline, "Settlement: reveal open");
        require(!iv.clearingPosted, "Settlement: clearing posted");
        require(inputRoot != bytes32(0) && resultHash != bytes32(0), "Settlement: empty roots");
        require(pRefPaise > 0 && pRefPaise <= pRetPaise, "Settlement: bad pRef");
        iv.clearingPosted = true;
        iv.inputRoot = inputRoot;
        iv.resultHash = resultHash;
        iv.pRefPaise = pRefPaise;
        emit ClearingPosted(id, inputRoot, resultHash, pRefPaise);
    }

    /**
     * @notice Settle a batch of cleared trades at pRef, moving escrow buyer → seller.
     * @param id Interval id.
     * @param trades Trade list (each settles at most once).
     */
    function settleBatch(uint256 id, Trade[] calldata trades)
        external
        onlyRole(OPERATOR_ROLE)
        nonReentrant
        whenNotPaused
    {
        Interval storage iv = intervals[id];
        require(iv.clearingPosted, "Settlement: no clearing");
        uint32 pRef = iv.pRefPaise;
        for (uint256 i = 0; i < trades.length; i++) {
            Trade calldata t = trades[i];
            require(t.pricePaise == pRef, "Settlement: price != pRef");
            require(t.qtyWh > 0, "Settlement: zero qty");
            require(t.buyer != address(0) && t.seller != address(0), "Settlement: parties");
            require(t.buyer != t.seller, "Settlement: self trade");
            // Only parties who committed in this interval can trade in it, so an operator key
            // cannot move escrow from an account that never took part.
            require(
                commits[id][t.buyer] != bytes32(0) && commits[id][t.seller] != bytes32(0),
                "Settlement: party not committed"
            );
            // The engine emits one trade per (buyer, seller) per interval; keying on the pair
            // (not qty) stops the same match being settled again with a different quantity.
            bytes32 key = _tradeKey(t);
            require(!tradeSettled[id][key], "Settlement: already settled");
            uint256 payment = _payment(t.qtyWh, t.pricePaise);
            require(escrow[t.buyer] >= payment, "Settlement: buyer escrow");
            tradeSettled[id][key] = true;
            escrow[t.buyer] -= payment;
            escrow[t.seller] += payment;
            emit TradeSettled(id, t.buyer, t.seller, t.qtyWh, t.pricePaise, payment);
        }
    }

    /**
     * @notice Post delivery Merkle root for the interval.
     * @param id Interval id.
     * @param deliveryRoot Root over delivery / shortfall leaves.
     */
    function postDelivery(uint256 id, bytes32 deliveryRoot)
        external
        onlyRole(OPERATOR_ROLE)
        whenNotPaused
    {
        Interval storage iv = intervals[id];
        require(iv.clearingPosted, "Settlement: no clearing");
        require(!iv.deliveryPosted, "Settlement: delivery posted");
        require(deliveryRoot != bytes32(0), "Settlement: empty root");
        iv.deliveryPosted = true;
        iv.deliveryRoot = deliveryRoot;
        emit DeliveryPosted(id, deliveryRoot);
    }

    /**
     * @notice Settle a Merkle-proved shortfall between one seller and one buyer from the
     *         seller's stake.
     * @dev Leaf = keccak256(abi.encode(intervalId, seller, buyer, shortfallWh)), one per
     *      (seller, buyer) pair, so every short-changed buyer is compensated.
     *      settleBatch charged the buyer for the full promised quantity, so the buyer first
     *      gets back what it paid for the undelivered energy, then the spec's compensation:
     *        refund       = shortfallWh * pRef / 1000
     *        compensation = shortfallWh * (pRet - pRef) / 1000
     *        penalty      = shortfallWh * pRef * f / 1000        (to treasury)
     *      The buyer ends up paying exactly pRef for what it was promised (spec, Phase 3).
     *      If the stake cannot cover everything, the buyer is paid first; nothing reverts.
     * @param id Interval id.
     * @param participant Under-delivering seller.
     * @param shortfallWh Undelivered Wh to this buyer.
     * @param proof Merkle proof against deliveryRoot.
     * @param buyer The short-changed buyer (part of the proven leaf).
     */
    function settleShortfall(
        uint256 id,
        address participant,
        uint64 shortfallWh,
        bytes32[] calldata proof,
        address buyer
    ) external onlyRole(OPERATOR_ROLE) nonReentrant whenNotPaused {
        Interval storage iv = intervals[id];
        require(iv.deliveryPosted, "Settlement: no delivery");
        require(shortfallWh > 0, "Settlement: zero shortfall");
        require(participant != address(0) && buyer != address(0), "Settlement: parties");
        require(participant != buyer, "Settlement: self trade");
        bytes32 pairKey = keccak256(abi.encode(participant, buyer));
        require(!shortfallSettled[id][pairKey], "Settlement: shortfall done");

        bytes32 leaf = keccak256(abi.encode(id, participant, buyer, shortfallWh));
        require(MerkleProof.verify(proof, iv.deliveryRoot, leaf), "Settlement: bad proof");

        shortfallSettled[id][pairKey] = true;
        _payShortfall(id, participant, buyer, shortfallWh, iv.pRefPaise);
    }

    function _payShortfall(uint256 id, address seller, address buyer, uint64 shortfallWh, uint32 pRef) internal {
        uint256 refund = (uint256(shortfallWh) * uint256(pRef)) / 1000;
        uint256 compensation = (uint256(shortfallWh) * uint256(pRetPaise - pRef)) / 1000;
        uint256 penalty = (uint256(shortfallWh) * uint256(pRef) * PENALTY_NUM) / (1000 * PENALTY_DEN);
        uint256 toBuyer = refund + compensation;

        // A shortfall too small to cost a whole paisa is recorded but moves nothing
        // (previously it reverted "zero slash" and could never be settled).
        uint256 slashed = (toBuyer + penalty) > 0 ? registry.slash(seller, toBuyer + penalty, address(this)) : 0;
        uint256 paid = slashed < toBuyer ? slashed : toBuyer;
        if (paid > 0) {
            token.safeTransfer(buyer, paid);
        }
        treasury += slashed - paid;

        emit ShortfallSettled(id, seller, buyer, shortfallWh, refund, compensation, penalty);
    }

    /**
     * @notice Move collected penalties out of the contract (admin). Cannot touch user escrow.
     */
    function sweepTreasury(address to, uint256 amount) external onlyRole(DEFAULT_ADMIN_ROLE) nonReentrant {
        require(to != address(0), "Settlement: to");
        require(amount > 0 && amount <= treasury, "Settlement: amount");
        treasury -= amount;
        token.safeTransfer(to, amount);
        emit TreasurySwept(to, amount);
    }

    /**
     * @notice Compute commit hash for client convenience / tests.
     */
    function computeCommitHash(
        uint256 intervalId,
        address participant,
        uint8 side,
        uint64 qtyWh,
        uint32 limitPricePaise,
        uint64 deadline,
        bytes32 salt
    ) external pure returns (bytes32) {
        return keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt));
    }

    /**
     * @notice Payment in paise for qtyWh at pricePaise/kWh (floor).
     */
    function paymentOf(uint64 qtyWh, uint32 pricePaise) external pure returns (uint256) {
        return _payment(qtyWh, pricePaise);
    }

    function _payment(uint64 qtyWh, uint32 pricePaise) internal pure returns (uint256) {
        return (uint256(qtyWh) * uint256(pricePaise)) / 1000;
    }

    function _tradeKey(Trade calldata t) internal pure returns (bytes32) {
        return keccak256(abi.encode(t.buyer, t.seller));
    }
}
