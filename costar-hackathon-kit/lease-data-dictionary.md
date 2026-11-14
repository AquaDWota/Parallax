# Lease DataFrame dictionary

Each row in `leases` is a tenancy with a recorded lease deal. `propertyId` identifies a building, so it can repeat for different tenants, historical periods, or renewals. This table excludes occupancies without a lease deal.

Dates describe the supplied snapshot; an open occupancy does not independently verify that a tenant is still there today. Missing values mean unreported, not necessarily zero. Numeric codes are field-specific: **0 means per square foot in rateAmountType**, but unknown in rateBasis. Never assume every 0 means unknown.

Contract rent, asking rent, effective rent, and proposed rent are different measures. Check currency, time basis, amount type, and service type before comparing. Lists remain lists in DataFrame cells. Fields may be absent if no record supplies them; nested asking-rate fields can coexist with an empty parent column.

This dictionary covers the lease table, not all fields in the building and related datasets. Source: `models/location-occupancy.md` and `schemas/location-occupancy.schema.json`.

| Variable | Simple meaning | Code values |
|---|---|---|
| `occupancyId` | Unique ID for this tenancy record. |  |
| `propertyId` | ID of the building or property. Repeats when a property has several tenancies. |  |
| `tenantName` | Name of the tenant company; blank when no matching company is known. |  |
| `occupancyFrom` | Start of the recorded tenancy period. |  |
| `occupancyTo` | End of the recorded tenancy period. Blank means the occupancy is open in this snapshot. |  |
| `occupiedSquareFeet` | Sum of reported occupied space sizes for this tenancy; may be incomplete if some sizes are missing. |  |
| `leaseDeal.askingRate.rateLow` | Lower end of the advertised rent range. |  |
| `leaseDeal.askingRate.rateHigh` | Upper end of the advertised rent range. |  |
| `leaseDeal.askingRate.rateBasis` | Whether the advertised asking rent is quoted monthly or yearly. | 0 = Unknown; 1 = Monthly; 2 = Yearly |
| `leaseDeal.askingRatePerMonth` | Asking rent expressed as a per-month total; mutually exclusive with the per-year and per-SF forms, set when an asking amount is entered. |  |
| `leaseDeal.askingRatePerYear` | Asking rent expressed as a per-year total; mutually exclusive with the per-month and per-SF forms, set when an asking amount is entered. |  |
| `leaseDeal.breakDates` | Dates and conditions for ending the lease early, stored as a list. |  |
| `leaseDeal.breakDatesState` | Whether break dates is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.businessRatesPerYear` | Annual business/property-tax charge recorded under business rates. |  |
| `leaseDeal.commencementDate` | Date the lease term begins; may differ from signing or moving in. |  |
| `leaseDeal.concessions` | Other benefits or incentives provided to the tenant, stored as a list. |  |
| `leaseDeal.contacts` | People connected to the deal, stored as a list. |  |
| `leaseDeal.effectiveRate` | Entered rent adjusted for concessions and other lease economics; separate from contract rent. |  |
| `leaseDeal.effectiveRateBasis` | Time period used for the entered effective rent. | 0 = Unknown; 1 = Monthly; 2 = Yearly |
| `leaseDeal.effectiveRateCalculatedBasis` | Basis used for calculated effective rent; see its code values. | 0 = Unknown; 1 = Monthly; 2 = Yearly |
| `leaseDeal.effectiveRatePerMonth` | User-entered effective rent expressed as a per-month total, the per-month form of the concession-and-escalation-adjusted effective rent. |  |
| `leaseDeal.effectiveRatePerYear` | User-entered effective rent expressed as a per-year total, the per-year form of the concession-and-escalation-adjusted effective rent. |  |
| `leaseDeal.expansionOptionComment` | Free-text comment describing the expansion-option terms. |  |
| `leaseDeal.expansionOptionDate` | Date the tenant may exercise the expansion option. |  |
| `leaseDeal.expansionOptionSquareFeet` | Square footage covered by the tenant's expansion option. |  |
| `leaseDeal.expansionOptionState` | Whether expansion option is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.expirationDate` | Scheduled end date of the lease. |  |
| `leaseDeal.freeMonths` | Number of months of free rent recorded. |  |
| `leaseDeal.freeRentMethodType` | How the free-rent benefit is applied. |  |
| `leaseDeal.freeRentSchedule` | Detailed periods of free rent, stored as a list. |  |
| `leaseDeal.grossAggregateValue` | Recorded total gross lease value over the term; see the source definition. |  |
| `leaseDeal.id` | Unique ID of the lease deal. |  |
| `leaseDeal.isLeaseTermMonthToMonth` | Whether the lease runs month to month. |  |
| `leaseDeal.leaseDealSourceType` | Source category for the recorded lease deal. | 0 = Unknown; 1 = PublicRecord_Foia; 2 = PublicRecord_SecFiling; 3 = PublicRecord_CmbsFiling; 6 = Media_NewsOutlets; 7 = ThirdParty_LandlordRep; 8 = Direct_Landlord; 9 = ThirdParty_TenantRep; 12 = Direct_Tenant; 14 = Direct_PressRelease; 15 = PublicRecord_CountyFiling; 16 = PublicRecord_Other; 17 = ThirdParty_Appraiser; 18 = ThirdParty_PressRelease; 19 = ThirdParty_PropertyManager; 20 = ThirdParty_Other; 21 = Direct_PowerBrokerSubmission; 26 = PublicRecord_HMLandRegistry; 27 = ThirdParty_Explore |
| `leaseDeal.leaseDealType` | Whether this is a new lease or a renewal. | 0 = Unknown; 1 = NewLease; 2 = Renewal |
| `leaseDeal.leaseTerm` | Length of the lease; read together with leaseTermType. |  |
| `leaseDeal.leaseTerminationOptionDate` | Recorded date associated with an early-termination option. |  |
| `leaseDeal.leaseTerminationOptionPenalty` | Free-text description of the penalty owed for exercising the early-termination option. |  |
| `leaseDeal.leaseTerminationOptionState` | Whether lease termination option is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.leaseTermType` | Unit or category for lease length, such as years or months. | 0 = Unknown; 1 = Years; 2 = Months; 3 = Days; 4 = ToBeDetermined; 5 = Negotiable; 6 = ThreeOrSixOrNine; 7 = ShortTerm |
| `leaseDeal.marketEffectiveRate` | Recorded market-effective rent measure. |  |
| `leaseDeal.marketEffectiveRatePerMonth` | Recorded market-effective rent on a monthly basis. |  |
| `leaseDeal.marketEffectiveRatePerYear` | Recorded market-effective rent on a yearly basis. |  |
| `leaseDeal.monetaryUnit` | Currency used for money amounts. | 0 = Unknown; 1 = UnitedStatesDollar; 2 = CanadianDollar; 3 = PoundSterling; 4 = Euro; 5 = AustralianDollar; 6 = BrazilianReal; 7 = SwissFranc; 8 = JapaneseYen; 9 = SingaporeDollar; 10 = HongKongDollar; 11 = ChineseYuan; 12 = UnitedArabEmiratesDirham; 13 = AfghanistanAfghani; 14 = AlbanianLek; 15 = ArmenianDram; 16 = NetherlandsAntilleanGuilder; 17 = AngolanKwanza; 18 = ArgentinaPeso; 19 = ArubanGuilder; 20 = AzerbaijanNewManat; 21 = BosnianMark; 22 = BarbadosDollar; 23 = BangladeshTaka; 24 = BulgarianLev; 25 = BurundiFranc; 26 = BermudianDollars; 27 = BruneiDollars; 28 = BolivianBoliviano; 29 = BahamianDollar; 30 = Bitcoin; 31 = BotswanianPula; 32 = BelarusianRuble; 33 = BelizeDollar; 34 = CongoleseFranc; 35 = ChileanPeso; 36 = ColombianPeso; 37 = CostaRicanColon; 38 = CubanPeso; 39 = CapeVerdeEscudo; 40 = CzechKoruna; 41 = DjiboutiFranc; 42 = DanishKrone; 43 = DominicanPeso; 44 = AlgerianDinar; 45 = EgyptianPound; 46 = EthiopianBirr; 47 = FijiDollars; 48 = GeorgianLari; 49 = GhanaianNewCedi; 50 = GambianDalasi; 51 = GuineanFranc; 52 = GuatemalanQuetzal; 53 = GuyanaDollar; 54 = HondurasLempira; 55 = CroatianKuna; 56 = HaitianGourde; 57 = HungarianForint; 58 = IndonesianRupiah; 59 = IsraeliShekel; 60 = IndianRupee; 61 = IraqiDinar; 62 = IranianRial; 63 = IcelandKrona; 64 = JamaicanDollar; 65 = JordanDinar; 66 = KenyanShilling; 67 = KyrgyzstaniSom; 68 = CambodiaRiel; 69 = ComorosFranc; 70 = SouthKoreanWon; 71 = KuwaitiDinar; 72 = CaymanIslandDollar; 73 = KazakhstaniTenge; 74 = LaoKip; 75 = LebanesePound; 76 = SriLankanRupee; 77 = LiberianDollar; 78 = LesothoLoti; 79 = LibyanDinar; 80 = MoroccanDirham; 81 = MoldovanLeu; 82 = MalagasyAriary; 83 = MyanmarKyat; 84 = MacauPataca; 85 = MauritanianQuguiya; 86 = MauritiusRupee; 87 = MaldivesRufiyaa; 88 = MalawiKwacha; 89 = MexicanPeso; 90 = MalaysianRinggit; 91 = MozambiqueNewMetical; 92 = NamibianDollar; 93 = NigerianNaira; 94 = NicaraguanCordobaOro; 95 = NorwegianKrone; 96 = NepalRupee; 97 = NewZealandDollar; 98 = OmaniRial; 99 = PanameanBalboa; 100 = PeruvianNuevoSol; 101 = PapuaNewGuineaKina; 102 = PhilippinePeso; 103 = PakistaniRupee; 104 = PolishZloty; 105 = ParaguayanGuarani; 106 = QatarRiyal; 107 = NewRomanianLeu; 108 = SerbianDinar; 109 = RussianRuble; 110 = RwandanFranc; 111 = SaudiRiyal; 112 = SolomonIslandsDollar; 113 = SeychellesRupee; 114 = SudanesePound; 115 = SwedishKrona; 116 = SierraLeoneLeone; 117 = SomaliShilling; 118 = SurinameDollar; 119 = SaoTomeanDobra; 120 = ElSalvadorColon; 121 = SwazilandLilangeni; 122 = ThailandBaht; 123 = TajikistanSomoni; 124 = TurkmenNewManat; 125 = TunisianDinar; 126 = TonganPaanga; 127 = TurkishLira; 128 = TrinidadianDollar; 129 = TaiwanDollar; 130 = TanzanianShilling; 131 = UkrainianHryvnia; 132 = UgandanShilling; 133 = UruguayPeso; 134 = UzbekistaniSom; 135 = VenezuelanBolivarSoberano; 136 = VietnameseDong; 137 = CentralAfricanFranc; 138 = EastCaribbeanDollar; 139 = WestAfricanFranc; 140 = FrenchPacificIslandsFranc; 141 = YemenRial; 142 = SouthAfricanRand; 143 = ZambianKwacha; 144 = BahrainiDinar; 145 = EritreanNakfa; 146 = FalklandIslandsPound; 147 = GibraltarPound; 148 = NorthKoreanWon; 149 = MongolianTughrik; 150 = SaintHelenaPound; 151 = SyrianPound; 152 = VanuatuVatu; 153 = ZimbabweanDollar; 154 = SamoanTala; 155 = BhutaneseNgultrum; 156 = MacedonianDenar |
| `leaseDeal.netAggregateValue` | Recorded total net lease value over the term; see the source definition. |  |
| `leaseDeal.noLandlordRepresentative` | Whether the record explicitly says the landlord has no representative. |  |
| `leaseDeal.noRateEscalation` | Whether the record explicitly says there are no rent increases. |  |
| `leaseDeal.noTenantRepresentative` | Whether the record explicitly says the tenant has no representative. |  |
| `leaseDeal.notes` | Additional recorded comments, stored as a list. |  |
| `leaseDeal.numRenewalOption` | Number of recorded options to renew. |  |
| `leaseDeal.numRenewalOptionComment` | Free-text comment describing the renewal-option terms. |  |
| `leaseDeal.percentageRent` | Percentage-rent rate: additional retail rent computed as a percentage of tenant sales above a breakpoint. Displayed as a % on the Lease Comps financial terms. |  |
| `leaseDeal.percentageRentBreakpoint` | Sales breakpoint above which percentage rent applies; the retail-lease threshold triggering overage rent. |  |
| `leaseDeal.propertyTaxAmount` | Property-tax amount allocated to the leased space as a tenant occupancy cost, shown on the Lease Comps financial terms ($/SF/Year). |  |
| `leaseDeal.propertyTaxAmountPerYear` | Annualized property-tax amount for the leased space; per-year form of the tenant's property-tax occupancy cost. |  |
| `leaseDeal.proposalEffectiveRate` | Effective rent for a proposed deal, rather than necessarily the signed terms. |  |
| `leaseDeal.proposalEffectiveRatePerMonth` | Proposed effective rent on a monthly basis. |  |
| `leaseDeal.proposalEffectiveRatePerYear` | Proposed effective rent on a yearly basis. |  |
| `leaseDeal.purchaseOptionComment` | Free-text comment describing the purchase-option terms. |  |
| `leaseDeal.purchaseOptionDate` | Date the tenant may exercise the purchase option. |  |
| `leaseDeal.purchaseOptionPrice` | Price at which the tenant may buy the property under a purchase option, when the lease has one. |  |
| `leaseDeal.purchaseOptionState` | Whether purchase option is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.rateActual` | Agreed contract rent. Read with rateBasis and rateAmountType. |  |
| `leaseDeal.rateActualIncreaseMethodType` | How increases to the contract rent are applied. | 0 = StepIncreases; 1 = ConsumerPriceIndexIncreases; 2 = ConsumerPriceIndexAndStepIncreases |
| `leaseDeal.rateActualPerMonth` | Actual contract rent expressed as a total per-month amount; mutually exclusive with per-year and per-SF forms, derived when rate is entered. |  |
| `leaseDeal.rateActualPerYear` | Actual contract rent expressed as a total per-year amount; mutually exclusive with the per-month and per-SF forms, derived when rate is entered. |  |
| `leaseDeal.rateAmountType` | How the rent amount is expressed, such as per square foot or a total monthly amount. | 0 = AmountPerSquareFoot; 1 = AmountPerMonth; 2 = AmountPerYear; 3 = AmountPerSquareMeter; 4 = AmountPerSeatPerMonth; 5 = AmountPerSeatPerYear; 6 = AmountPerKilowatt |
| `leaseDeal.rateBasis` | Whether the contract rent is quoted monthly or yearly; not the number of rentals. | 0 = Unknown; 1 = Monthly; 2 = Yearly |
| `leaseDeal.rateEscalations` | Scheduled rent increases, stored as a list. |  |
| `leaseDeal.renewalOptionDate` | Recorded date associated with the renewal option. |  |
| `leaseDeal.renewalOptionState` | Whether renewal option is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.renewalOptionTermInMonths` | Length of the optional renewal period, in months. |  |
| `leaseDeal.rentPlus` | Additional rent-plus amount layered on base rent (e.g. TMI = taxes, maintenance, insurance pass-throughs); a supplemental occupancy charge shown alongside CAM/additional rent on the Lease Comps financial terms. |  |
| `leaseDeal.reviewDates` | Collection of UK rent-review dates at which the contract rent is reset; paired with reviewPatternYears and reviewDatesState. |  |
| `leaseDeal.reviewDatesState` | Whether review dates is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.reviewPatternYears` | UK rent-review cadence in years (interval between contractual rent reviews). |  |
| `leaseDeal.rightOfFirstOfferComment` | Free-text comment describing the right-of-first-offer terms. |  |
| `leaseDeal.rightOfFirstOfferState` | Whether right of first offer is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.rightOfFirstRefusalComment` | Free-text comment describing the right-of-first-refusal terms. |  |
| `leaseDeal.rightOfFirstRefusalSquareFeet` | Area covered by a right of first refusal. |  |
| `leaseDeal.rightOfFirstRefusalState` | Whether right of first refusal is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.serviceChargeAmount` | Recorded service charge amount; check its basis before comparing. |  |
| `leaseDeal.serviceChargeAmountPerYear` | Recorded annual service charge. |  |
| `leaseDeal.serviceChargeState` | Whether service charge is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.serviceType` | Which operating expenses are included in rent or paid separately by the tenant. | 0 = Unknown; 1 = PlusCleaning; 2 = PlusElectricAndCleaning; 4 = PlusElectric; 5 = UtilitiesAndChar; 6 = PlusUtilities; 7 = FullService; 8 = IndustrialGross; 9 = ModifiedGross; 10 = Net; 11 = Negotiable; 12 = DoubleNet; 13 = TripleNet; 14 = ToBeDetermined; 15 = TenantElectric; 16 = FullyRepairingAndInsuring; 17 = InternalRepairingOnly; 18 = InternalRepairingAndInsuring; 19 = FullServiceGrossNoPass; 20 = ChargesAndTaxesExcluded; 21 = PlusTaxes; 22 = ChargesAndTaxesIncluded; 23 = PlusCharges |
| `leaseDeal.signagePayerType` | Who pays for signage. | 0 = Unknown; 1 = Landlord; 2 = Tenant |
| `leaseDeal.signageState` | Whether signage is recorded as applying (unknown / yes / no). | 0 = Unknown; 1 = Yes; 2 = No |
| `leaseDeal.signDate` | Date the lease agreement was signed. |  |
| `leaseDeal.sourceTypes` | Codes describing the sources of the lease information. |  |
| `leaseDeal.spaceType` | Category of space involved in the lease. | 0 = Unknown; 1 = Relet; 2 = New; 3 = Sublet; 4 = Assignment |
| `leaseDeal.spaceUse` | How the leased space is used. | 0 = Unknown; 1 = Office; 2 = OfficeMedical; 3 = OfficeRetail; 4 = Medical; 5 = Retail; 6 = Flex; 7 = Industrial |
| `leaseDeal.spreadOverTermType` | How a benefit or adjustment is spread across the lease term. | 0 = EnterByMonth; 1 = EnterByDate |
| `leaseDeal.tenantImprovementAllowancePerSquareFeet` | Landlord contribution toward tenant improvements per square foot. |  |
| `leaseDeal.zoneARent` | Zone A rent: UK retail rental valuation method pricing the most valuable front-of-shop zone per square foot; only valid when the space use is Retail. |  |
