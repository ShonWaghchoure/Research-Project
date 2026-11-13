// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title MockINR
 * @notice Test INR token with 2 decimals (1 unit = 1 paisa) and a daily faucet.
 */
contract MockINR is ERC20, Ownable {
    /// @notice Maximum faucet mint per address per UTC day (in paise).
    uint256 public immutable faucetAmount;

    /// @dev day index (timestamp / 1 days) => address => already claimed
    mapping(uint256 => mapping(address => bool)) private _claimedDay;

    /// @notice Emitted when an address claims from the faucet.
    event FaucetClaimed(address indexed account, uint256 amount, uint256 day);

    /**
     * @param faucetAmount_ Paise minted per successful faucet claim.
     */
    constructor(uint256 faucetAmount_) ERC20("Mock INR", "mINR") Ownable(msg.sender) {
        require(faucetAmount_ > 0, "MockINR: zero faucet");
        faucetAmount = faucetAmount_;
    }

    /// @inheritdoc ERC20
    function decimals() public pure override returns (uint8) {
        return 2;
    }

    /**
     * @notice Mint `faucetAmount` to the caller once per UTC day.
     */
    function faucet() external {
        uint256 day = block.timestamp / 1 days;
        require(!_claimedDay[day][msg.sender], "MockINR: already claimed today");
        _claimedDay[day][msg.sender] = true;
        _mint(msg.sender, faucetAmount);
        emit FaucetClaimed(msg.sender, faucetAmount, day);
    }

    /**
     * @notice Operator mint for tests and demos.
     * @param to Recipient.
     * @param amount Paise to mint.
     */
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }

    /**
     * @notice Whether `account` has claimed the faucet for the current UTC day.
     */
    function hasClaimedToday(address account) external view returns (bool) {
        return _claimedDay[block.timestamp / 1 days][account];
    }
}
